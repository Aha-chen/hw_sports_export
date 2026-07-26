import pyzipper
import json
import os
import re
from bisect import bisect_left
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import math
import concurrent.futures
import xml.etree.ElementTree as ET
from timezonefinder import TimezoneFinder

MAX_JSON_SIZE = 512 * 1024 * 1024

# Instantiate TimezoneFinder globally
tf = TimezoneFinder()

# --- Exact GCJ-02 to WGS-84 Coordinate Conversion ---
pi = 3.1415926535897932384626
a = 6378245.0
ee = 0.00669342162296594323

def out_of_china(lng, lat):
    if lng < 72.004 or lng > 137.8347: return True
    if lat < 0.8293 or lat > 55.8271: return True
    return False

def transform_lat(lng, lat):
    ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * pi) + 20.0 * math.sin(2.0 * lng * pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lat * pi) + 40.0 * math.sin(lat / 3.0 * pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(lat / 12.0 * pi) + 320 * math.sin(lat * pi / 30.0)) * 2.0 / 3.0
    return ret

def transform_lng(lng, lat):
    ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(math.fabs(lng))
    ret += (20.0 * math.sin(6.0 * lng * pi) + 20.0 * math.sin(2.0 * lng * pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(lng * pi) + 40.0 * math.sin(lng / 3.0 * pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(lng / 12.0 * pi) + 300.0 * math.sin(lng / 30.0 * pi)) * 2.0 / 3.0
    return ret

def wgs84_to_gcj02(lng, lat):
    if out_of_china(lng, lat): return lng, lat
    dlat = transform_lat(lng - 105.0, lat - 35.0)
    dlng = transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * pi)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * pi)
    mglat = lat + dlat
    mglng = lng + dlng
    return mglng, mglat

def gcj02_to_wgs84_exact(gcjLon, gcjLat):
    if out_of_china(gcjLon, gcjLat): return gcjLon, gcjLat
    
    initDelta = 0.01
    threshold = 0.000000001
    dLat = initDelta
    dLon = initDelta
    mLat = gcjLat - dLat
    mLon = gcjLon - dLon
    pLat = gcjLat + dLat
    pLon = gcjLon + dLon
    wgsLat = 0
    wgsLon = 0
    for _ in range(1000):
        wgsLat = (mLat + pLat) / 2
        wgsLon = (mLon + pLon) / 2
        tmpLon, tmpLat = wgs84_to_gcj02(wgsLon, wgsLat)
        dLat = tmpLat - gcjLat
        dLon = tmpLon - gcjLon
        if abs(dLat) < threshold and abs(dLon) < threshold:
            break
        if dLat > 0: pLat = wgsLat
        else: mLat = wgsLat
        if dLon > 0: pLon = wgsLon
        else: mLon = wgsLon
    return wgsLon, wgsLat

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlam = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi/2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam/2.0)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def fix_json_content(content):
    """Fix Huawei's non-standard JSON: unescaped newlines in string values and unquoted numeric keys."""
    # Try parsing as-is first; only apply fixes if needed
    try:
        json.loads(content)
        return content
    except json.JSONDecodeError:
        pass
    # Escape literal newlines only inside JSON strings. Replacing all
    # newlines would corrupt normal whitespace between JSON tokens.
    chars = []
    in_string = False
    escaped = False
    for char in content:
        if char == '"' and not escaped:
            in_string = not in_string
        if char == '\n' and in_string:
            chars.append('\\n')
        elif char == '\r' and in_string:
            chars.append('\\r')
        else:
            chars.append(char)
        if char == '\\' and not escaped:
            escaped = True
        else:
            escaped = False
    fixed = ''.join(chars)
    fixed = re.sub(r'([{,])\s*([0-9]+(?:\.[0-9]+)?)\s*:', r'\1"\2":', fixed)
    return fixed

def get_sport_type_string(sport_type_code):
    mapping = {
        1: 'Stairs_Climb', 2: 'Mountain_Climb', 3: 'Cycling', 4: 'Running',
        5: 'Walking', 7: 'Rowing', 8: 'Elliptical', 9: 'Swimming',
        10: 'Fitness', 11: 'Yoga', 12: 'HIIT', 13: 'Jump_Rope',
        14: 'Strength', 16: 'Spinning', 101: 'Indoor_Running',
        256: 'Indoor_Running_Old',
    }
    return mapping.get(sport_type_code, f'Workout_{sport_type_code}')

# Strava TCX only recognizes: Biking, Running, Hiking, Walking, Swimming
# All other values default to Running, so we map explicitly
STRAVA_TCX_SPORT_MAP = {
    'Running': 'Running',
    'Indoor_Running': 'Running',
    'Indoor_Running_Old': 'Running',
    'Cycling': 'Biking',
    'Spinning': 'Biking',
    'Walking': 'Walking',
    'Stairs_Climb': 'Hiking',
    'Mountain_Climb': 'Hiking',
    'Swimming': 'Swimming',
}

def get_closest_val(t, sorted_keys, data_dict, max_diff=10):
    """Binary search for the closest key to t. sorted_keys must be pre-sorted."""
    if not sorted_keys: return None
    idx = bisect_left(sorted_keys, t)
    candidates = []
    if idx < len(sorted_keys): candidates.append(sorted_keys[idx])
    if idx > 0: candidates.append(sorted_keys[idx - 1])
    closest_t = min(candidates, key=lambda k: abs(k - t))
    if abs(closest_t - t) <= max_diff:
        return data_dict[closest_t]
    return None


def utc_iso(timestamp):
    """Return the TCX-friendly UTC representation used for all timestamps."""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace('+00:00', 'Z')

def process_single_activity(activity, start_ts, end_ts, output_dir):
    start_time_ms = activity.get('startTime', 0)
    if start_ts and start_time_ms < start_ts: return None
    if end_ts and start_time_ms > end_ts: return None
        
    sport_type = activity.get('sportType', 0)
    sport_name = get_sport_type_string(sport_type)
    
    attr = activity.get('attribute', '')
    
    # Summary Metrics
    summary_hr, summary_cadence = None, None
    if 'HW_EXT_TRACK_SIMPLIFY@is' in attr:
        try:
            summary_part = attr.split('HW_EXT_TRACK_SIMPLIFY@is')[1].split('&&')[0]
            summary_data = json.loads(summary_part)
            summary_hr = summary_data.get('avgHeartRate')
            summary_cadence = summary_data.get('avgStepRate')
            if not summary_cadence and 'mExtendTrackDataMap' in summary_data:
                cad_str = summary_data['mExtendTrackDataMap'].get('crossTrainerCadence')
                if cad_str: summary_cadence = int(cad_str)
        except: pass

    # Extract Data Arrays
    hr_data, cad_data, alti_data, pm_data = {}, {}, {}, {}
    gps_data = []
    section_data = []  # Manual lap splits from tp=sec

    parts = attr.split('HW_EXT_TRACK_DETAIL@')
    if len(parts) >= 2:
        track_lines = parts[1].split('&&')[0].split('\n')
        for line in track_lines:
            if not line.strip(): continue
            p_parts = line.split(';')
            tp = None
            for p in p_parts:
                if p.startswith('istp=') or p.startswith('tp='):
                    tp = p.split('=')[1]
                    break
            
            if tp == 'lbs':
                lat, lon, alt, t_sec = None, None, None, None
                for p in p_parts:
                    if '=' not in p: continue
                    k, v = p.split('=', 1)
                    if k == 'lat': lat = float(v)
                    elif k == 'lon': lon = float(v)
                    elif k == 'alt': alt = float(v)
                    elif k == 't': t_sec = int(float(v))
                if lat is not None and lon is not None and t_sec is not None:
                    gps_data.append({'t': t_sec, 'lat': lat, 'lon': lon, 'alt': alt})
            elif tp == 'h-r':
                t_ms, v = None, None
                for p in p_parts:
                    if '=' not in p: continue
                    k, val = p.split('=', 1)
                    if k == 'k': t_ms = int(val)
                    elif k == 'v': v = float(val)
                if t_ms is not None and v is not None: hr_data[int(t_ms/1000)] = v
            elif tp == 's-r':
                t_ms, v = None, None
                for p in p_parts:
                    if '=' not in p: continue
                    k, val = p.split('=', 1)
                    if k == 'k': t_ms = int(val)
                    elif k == 'v': v = float(val)
                if t_ms and v is not None: cad_data[int(t_ms/1000)] = v
            elif tp == 'alti':
                t_ms, v = None, None
                for p in p_parts:
                    if '=' not in p: continue
                    k, val = p.split('=', 1)
                    if k == 'k': t_ms = int(val)
                    elif k == 'v': v = float(val)
                if t_ms and v is not None: alti_data[int(t_ms/1000)] = v
            elif tp == 'p-m':
                # k is distance in mm (e.g. 10000000 = 10km, actually 1km based on totalDistance matching)
                # Huawei distance k is 10,000,000 for 1km. So dist_m = k / 10000
                k_val, v_val = None, None
                for p in p_parts:
                    if '=' not in p: continue
                    k, val = p.split('=', 1)
                    if k == 'k': k_val = int(val)
                    elif k == 'v': v_val = float(val)
                if k_val is not None and v_val is not None: pm_data[k_val] = v_val
            elif tp == 'sec':
                # Manual lap split: sn=seq, st=time(s), sd=dist(cm), sp=pace(s/km), shr=hr, sc=cadence
                sec = {}
                for p in p_parts:
                    if '=' not in p: continue
                    k, val = p.split('=', 1)
                    if k in ('sn', 'st', 'sd', 'sp', 'shr', 'sc'):
                        try: sec[k] = float(val)
                        except: pass
                if 'sn' in sec:
                    section_data.append(sec)

    gps_data.sort(key=lambda x: x['t'])
    section_data.sort(key=lambda x: x.get('sn', 0))

    # Pre-sort keys for binary search in get_closest_val
    hr_keys = sorted(hr_data.keys())
    cad_keys = sorted(cad_data.keys())
    alti_keys = sorted(alti_data.keys())

    # Filter out obvious GPS outliers (e.g. 0,0) before proceeding
    valid_gps_data = [pt for pt in gps_data if 'lat' in pt and 'lon' in pt and (abs(pt['lat']) > 0.1 or abs(pt['lon']) > 0.1)]
    gps_data = valid_gps_data

    # Determine timezone dynamically based on the first valid GPS point
    local_tz = timezone(timedelta(hours=8)) # Fallback to UTC+8
    if len(gps_data) > 0:
        first_pt = gps_data[0]
        # We need WGS84 for timezonefinder, so do a quick conversion of the first point
        first_wgs_lon, first_wgs_lat = gcj02_to_wgs84_exact(first_pt['lon'], first_pt['lat'])
        tz_name = tf.timezone_at(lng=first_wgs_lon, lat=first_wgs_lat)
        if tz_name:
            try:
                local_tz = ZoneInfo(tz_name)
            except Exception:
                pass

    try:
        start_dt_act = datetime.fromtimestamp(start_time_ms / 1000.0, tz=local_tz)
        date_str = start_dt_act.strftime('%Y%m%d_%H%M%S')
        display_date = start_dt_act.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        start_dt_act = datetime.fromtimestamp(start_time_ms / 1000.0, tz=timezone.utc)
        date_str = str(start_time_ms)
        display_date = date_str

    watch_total_dist = activity.get('totalDistance', 0)
    watch_total_time_s = activity.get('totalTime', 0) / 1000.0
    cum_dist = 0.0
    last_hr, last_cad, last_alti = None, None, None

    # Convert all points to WGS-84 first, before calculating distances
    for pt in gps_data:
        pt['wgs_lon'], pt['wgs_lat'] = gcj02_to_wgs84_exact(pt['lon'], pt['lat'])

    previous_valid_pt = None
    for pt in gps_data:
        if previous_valid_pt is not None:
            prev = previous_valid_pt
            dist = haversine_distance(prev['wgs_lat'], prev['wgs_lon'],
                                         pt['wgs_lat'], pt['wgs_lon'])
            if dist < 1000:
                cum_dist += dist
            else:
                # A large jump is normally a GPS reconnect/outlier. Do not let
                # the next point measure from the stale, pre-jump position.
                # The watch total is used below to calibrate the accepted path.
                previous_valid_pt = pt
            if dist < 1000:
                previous_valid_pt = pt
        else:
            previous_valid_pt = pt
        pt['cum_dist'] = cum_dist
        
        hr = get_closest_val(pt['t'], hr_keys, hr_data)
        if hr is not None: last_hr = hr
        pt['hr'] = hr if hr is not None else last_hr

        cad = get_closest_val(pt['t'], cad_keys, cad_data)
        if cad is not None: last_cad = cad
        pt['cad'] = cad if cad is not None else last_cad

        alti = get_closest_val(pt['t'], alti_keys, alti_data)
        if alti is not None: last_alti = alti
        pt['alti'] = alti if alti is not None else (pt['alt'] if pt['alt'] is not None else last_alti)
        
    if cum_dist > 0 and watch_total_dist > 0:
        scale_factor = watch_total_dist / cum_dist
        for pt in gps_data:
            pt['scaled_dist'] = pt['cum_dist'] * scale_factor
    else:
        for pt in gps_data:
            pt['scaled_dist'] = pt['cum_dist']

    points_added = len(gps_data)
    final_trackpoints = []
    
    last_written_t = None
    for pt in gps_data:
        if last_written_t is not None and pt['t'] <= last_written_t:
            pt['t'] = last_written_t + 0.1
        last_written_t = pt['t']
        
        final_hr = pt['hr'] if pt['hr'] is not None else summary_hr
        final_cad = pt['cad'] if pt['cad'] is not None else summary_cadence
        
        final_trackpoints.append({
            'time': utc_iso(pt['t']),
            'lat': pt['wgs_lat'],
            'lon': pt['wgs_lon'],
            'alti': pt['alti'],
            'dist': pt['scaled_dist'],
            'hr': final_hr,
            'cad': final_cad
        })

    # Huawei's GPS stream can start a few seconds late or end after the
    # activity summary. The summary duration is the authoritative activity
    # duration, so normalize the outdoor time axis to startTime + totalTime.
    # This keeps Lap durations and TCX activity duration consistent without
    # changing the spatial track or sensor values.
    if len(final_trackpoints) > 1 and watch_total_time_s > 0:
        source_start = datetime.fromisoformat(final_trackpoints[0]['time']).timestamp()
        source_end = datetime.fromisoformat(final_trackpoints[-1]['time']).timestamp()
        source_duration = source_end - source_start
        if source_duration > 0:
            activity_start = start_time_ms / 1000.0
            for point in final_trackpoints:
                point_ts = datetime.fromisoformat(point['time']).timestamp()
                normalized_ts = activity_start + (point_ts - source_start) * watch_total_time_s / source_duration
                point['time'] = utc_iso(normalized_ts)

    # Indoor Running / Missing GPS Fallback
    if points_added == 0 and (sport_type == 101 or sport_type == 256):
        total_time_s = watch_total_time_s
        if total_time_s < 2:
            total_time_s = 60
            
        start_time_s = start_time_ms / 1000.0
        
        # Method 1: Generate trackpoints strictly based on p-m (pace/distance) nodes to preserve exact pace curve
        if pm_data and watch_total_dist > 0:
            pm_keys = sorted(list(pm_data.keys()))
            current_t = start_time_s
            current_dist = 0.0

            # Always include the activity start as a zero-distance anchor so
            # the first Lap duration/distance is not understated by the first
            # 5-second sampling step.
            final_trackpoints.append({
                'time': utc_iso(start_time_s),
                'dist': 0.0,
                'hr': get_closest_val(current_t, hr_keys, hr_data, max_diff=15),
                'cad': get_closest_val(current_t, cad_keys, cad_data, max_diff=15)
            })
            points_added += 1
            
            for k_val in pm_keys:
                # v is pace in seconds per km (e.g. 424.0 -> 7:04/km)
                pace_s_per_km = pm_data[k_val]
                
                # target distance in meters (k_val is 10,000,000 per 1km -> k_val / 10000 = meters)
                target_dist_m = k_val / 10000.0
                
                # Sometimes the last node exceeds watch_total_dist slightly, cap it
                if target_dist_m > watch_total_dist:
                    target_dist_m = watch_total_dist
                    
                segment_dist_m = target_dist_m - current_dist
                if segment_dist_m <= 0:
                    continue
                    
                # Time spent in this segment
                # pace is sec/km. So sec/m = pace / 1000
                segment_time_s = segment_dist_m * (pace_s_per_km / 1000.0)
                
                # To make the pace look smooth in Strava, we need to inject points every N seconds
                # rather than just 1 point per kilometer. Let's insert a point every 5 seconds.
                step_s = 5.0
                num_steps = int(segment_time_s / step_s)
                
                if num_steps <= 0:
                    num_steps = 1
                    step_s = segment_time_s
                    
                dist_step = segment_dist_m / num_steps
                
                for step in range(num_steps):
                    current_t += step_s
                    current_dist += dist_step
                    
                    hr = get_closest_val(current_t, hr_keys, hr_data, max_diff=15)
                    cad = get_closest_val(current_t, cad_keys, cad_data, max_diff=15)
                    
                    if hr is not None: last_hr = hr
                    if cad is not None: last_cad = cad
                    
                    final_trackpoints.append({
                        'time': datetime.fromtimestamp(current_t, tz=timezone.utc).isoformat(),
                        'dist': current_dist,
                        'hr': hr if hr is not None else last_hr,
                        'cad': cad if cad is not None else last_cad
                    })
                    points_added += 1
                    
            # The watch duration is authoritative. Pace nodes describe the
            # distance profile, but can cover a different amount of elapsed
            # time due to rounding or export gaps. Re-time the generated
            # points so the final point is exactly at activity end.
            final_time = start_time_s + total_time_s
            if final_trackpoints:
                generated_start = start_time_s
                generated_end = current_t
                generated_duration = generated_end - generated_start
                if generated_duration > 0 and abs(generated_duration - total_time_s) > 0.001:
                    time_scale = total_time_s / generated_duration
                    for point in final_trackpoints:
                        point_t = datetime.fromisoformat(point['time']).timestamp()
                        point_t = generated_start + (point_t - generated_start) * time_scale
                        point['time'] = utc_iso(point_t)
                if datetime.fromisoformat(final_trackpoints[-1]['time'].replace('Z', '+00:00')).timestamp() < final_time:
                    final_trackpoints.append({
                        'time': utc_iso(final_time),
                        'dist': watch_total_dist,
                        'hr': last_hr,
                        'cad': last_cad
                    })
                    points_added += 1
                else:
                    # Guard against floating point drift and ensure the final
                    # distance is exactly the watch total.
                    final_trackpoints[-1]['time'] = utc_iso(final_time)
                    final_trackpoints[-1]['dist'] = watch_total_dist
                
        else:
            # Method 2: Fallback to old pro-rata method using hr/cad timestamps if no p-m data
            indoor_times = set(hr_data.keys()).union(set(cad_data.keys()))
            
            if len(indoor_times) > 2:
                sorted_times = sorted(list(indoor_times))
                valid_times = [t for t in sorted_times if start_time_s <= t <= start_time_s + total_time_s + 60]
                
                if len(valid_times) > 2:
                    actual_duration = valid_times[-1] - valid_times[0]
                    
                    for t in valid_times:
                        progress = (t - valid_times[0]) / actual_duration if actual_duration > 0 else 0
                        current_dist = watch_total_dist * progress
                        
                        hr = get_closest_val(t, hr_keys, hr_data, max_diff=15)
                        cad = get_closest_val(t, cad_keys, cad_data, max_diff=15)
                        
                        if hr is not None: last_hr = hr
                        if cad is not None: last_cad = cad
                        
                        final_trackpoints.append({
                            'time': datetime.fromtimestamp(t, tz=timezone.utc).isoformat(),
                            'dist': current_dist,
                            'hr': hr if hr is not None else last_hr,
                            'cad': cad if cad is not None else last_cad
                        })
                        points_added += 1
                        
            if points_added == 0:
                start_time_iso = utc_iso(start_time_ms / 1000.0)
                end_time_iso = utc_iso(start_time_ms / 1000.0 + total_time_s)
                
                final_trackpoints.append({
                    'time': start_time_iso,
                    'dist': 0.0,
                    'hr': summary_hr,
                    'cad': summary_cadence
                })
                final_trackpoints.append({
                    'time': end_time_iso,
                    'dist': watch_total_dist,
                    'hr': summary_hr,
                    'cad': summary_cadence
                })
                points_added = 2

    if points_added > 0:
        filename = f"strava_{sport_name}_{date_str}.tcx"
        filepath = os.path.join(output_dir, filename)

        NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
        ET.register_namespace("", NS)
        root = ET.Element(f"{{{NS}}}TrainingCenterDatabase")
        activities = ET.SubElement(root, f"{{{NS}}}Activities")
        # Do not silently relabel an unknown Huawei sport as running. The
        # explicit map below preserves the activity semantics; unsupported
        # sports remain "Other" and can be handled by a future policy choice.
        tcx_sport = STRAVA_TCX_SPORT_MAP.get(sport_name, 'Other')
        act_node = ET.SubElement(activities, f"{{{NS}}}Activity", Sport=tcx_sport)

        start_time_iso = final_trackpoints[0]['time']
        ET.SubElement(act_node, f"{{{NS}}}Id").text = start_time_iso

        total_calories = int(activity.get('totalCalories', 0) / 1000.0)

        # Split trackpoints into laps
        # Priority: manual sections (tp=sec) > auto 1km splits
        laps = []

        if section_data and len(final_trackpoints) > 2:
            # Use manual sections: split trackpoints by cumulative distance boundaries
            sec_boundaries = []  # cumulative distance at each section end (in meters)
            cum = 0.0
            for sec in section_data:
                cum += sec.get('sd', 0) / 100.0  # sd is in cm
                sec_boundaries.append(cum)

            boundary_idx = 0
            current_lap_pts = []
            for pt in final_trackpoints:
                current_lap_pts.append(pt)
                if boundary_idx < len(sec_boundaries) and pt['dist'] >= sec_boundaries[boundary_idx]:
                    laps.append(current_lap_pts)
                    # Do not create a trailing zero-length lap when the
                    # boundary is exactly the final point.
                    current_lap_pts = [] if pt is final_trackpoints[-1] else [pt]
                    boundary_idx += 1
            if current_lap_pts:
                laps.append(current_lap_pts)
        else:
            # Fallback: auto split by 1km
            current_lap_pts = []
            next_lap_dist = 1000.0

            for pt in final_trackpoints:
                current_lap_pts.append(pt)
                if pt['dist'] >= next_lap_dist and len(final_trackpoints) > 2:
                    if pt is not final_trackpoints[-1]:
                        laps.append(current_lap_pts)
                        current_lap_pts = [pt]
                    else:
                        current_lap_pts = []
                    next_lap_dist += 1000.0
            if current_lap_pts:
                laps.append(current_lap_pts)

        if len(laps) == 0:
            laps = [final_trackpoints]

        for lap_pts in laps:
            lap_start_time = lap_pts[0]['time']
            lap_start_dist = lap_pts[0]['dist']
            lap_end_dist = lap_pts[-1]['dist']
            lap_dist = lap_end_dist - lap_start_dist

            # Calculate lap duration from timestamps
            try:
                t0 = datetime.fromisoformat(lap_pts[0]['time'])
                t1 = datetime.fromisoformat(lap_pts[-1]['time'])
                lap_time_s = (t1 - t0).total_seconds()
            except Exception:
                lap_time_s = watch_total_time_s / max(len(laps), 1)

            # Proportional calorie split
            lap_cal = int(total_calories * (lap_dist / watch_total_dist)) if watch_total_dist > 0 else 0

            lap_node = ET.SubElement(act_node, f"{{{NS}}}Lap", StartTime=lap_start_time)
            ET.SubElement(lap_node, f"{{{NS}}}TotalTimeSeconds").text = str(max(lap_time_s, 0))
            ET.SubElement(lap_node, f"{{{NS}}}DistanceMeters").text = str(lap_dist)
            ET.SubElement(lap_node, f"{{{NS}}}Calories").text = str(lap_cal)
            ET.SubElement(lap_node, f"{{{NS}}}Intensity").text = "Active"
            ET.SubElement(lap_node, f"{{{NS}}}TriggerMethod").text = "Manual" if section_data else "Distance"

            track_node = ET.SubElement(lap_node, f"{{{NS}}}Track")

            for pt in lap_pts:
                tp_node = ET.SubElement(track_node, f"{{{NS}}}Trackpoint")
                ET.SubElement(tp_node, f"{{{NS}}}Time").text = pt['time']

                if 'lat' in pt and pt['lat'] is not None and 'lon' in pt and pt['lon'] is not None:
                    pos_node = ET.SubElement(tp_node, f"{{{NS}}}Position")
                    ET.SubElement(pos_node, f"{{{NS}}}LatitudeDegrees").text = str(pt['lat'])
                    ET.SubElement(pos_node, f"{{{NS}}}LongitudeDegrees").text = str(pt['lon'])

                if pt.get('alti') is not None:
                    ET.SubElement(tp_node, f"{{{NS}}}AltitudeMeters").text = str(pt['alti'])

                ET.SubElement(tp_node, f"{{{NS}}}DistanceMeters").text = str(pt['dist'])

                if pt.get('hr') is not None:
                    hr_node = ET.SubElement(tp_node, f"{{{NS}}}HeartRateBpm")
                    ET.SubElement(hr_node, f"{{{NS}}}Value").text = str(int(pt['hr']))

                if pt.get('cad') is not None:
                    # Huawei reports bilateral steps/min for running/walking.
                    # Strava reads running cadence from the ActivityExtension
                    # RunCadence element, whose value is single-foot cadence.
                    cad_val = int(pt['cad'] / 2) if sport_type in (4, 5, 101, 256) else int(pt['cad'])
                    if sport_type in (4, 5, 101, 256):
                        EXT_NS = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"
                        ET.register_namespace('ext', EXT_NS)
                        extensions = ET.SubElement(tp_node, f"{{{NS}}}Extensions")
                        tpx = ET.SubElement(extensions, f"{{{EXT_NS}}}TPX")
                        ET.SubElement(tpx, f"{{{EXT_NS}}}RunCadence").text = str(cad_val)
                    else:
                        ET.SubElement(tp_node, f"{{{NS}}}Cadence").text = str(cad_val)

        xml_str = ET.tostring(root, encoding="utf-8", xml_declaration=True).decode('utf-8')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(xml_str)
            
        # Downsample GPS points for frontend overview
        overview_path = []
        if sport_type not in (101, 256) and len(gps_data) > 0:
            # Take up to 1000 evenly spaced points for the summary to ensure high fidelity
            step = max(1, len(gps_data) // 1000)
            for i in range(0, len(gps_data), step):
                pt = gps_data[i]
                if 'wgs_lat' in pt and 'wgs_lon' in pt:
                    overview_path.append([pt['wgs_lat'], pt['wgs_lon']])

        # 生成心率/配速图表数据（降采样到最多 200 个点，使用滑动窗口计算配速）
        hr_series = []
        pace_series = []

        if len(final_trackpoints) > 0:
            # 降采样步长（增加到 200 个点以获得更精细的曲线）
            chart_step = max(1, len(final_trackpoints) // 200)

            # 配速计算窗口大小（用于平滑瞬时配速）
            pace_window = max(10, len(final_trackpoints) // 50)  # 约 50 个窗口

            for i in range(0, len(final_trackpoints), chart_step):
                pt = final_trackpoints[i]

                # 计算时间（相对于活动开始的秒数）
                try:
                    pt_time = datetime.fromisoformat(pt['time'])
                    start_time = datetime.fromisoformat(final_trackpoints[0]['time'])
                    elapsed_s = (pt_time - start_time).total_seconds()
                except Exception:
                    elapsed_s = i * 5  # 估算

                # 格式化时间为 mm:ss
                elapsed_min = int(elapsed_s // 60)
                elapsed_sec = int(elapsed_s % 60)
                time_str = f"{elapsed_min}:{elapsed_sec:02d}"

                # 心率数据点
                if pt.get('hr') is not None:
                    hr_series.append({
                        "time": time_str,
                        "elapsed": elapsed_s,
                        "hr": int(pt['hr'])
                    })

                # 配速数据点（使用滑动窗口计算瞬时配速，更平滑）
                if pt.get('dist') is not None and i >= pace_window:
                    try:
                        # 取窗口前缘的点
                        window_start_idx = max(0, i - pace_window)
                        prev_pt = final_trackpoints[window_start_idx]
                        prev_time = datetime.fromisoformat(prev_pt['time'])
                        delta_s = (pt_time - prev_time).total_seconds()
                        delta_dist = pt['dist'] - prev_pt['dist']
                        if delta_s > 0 and delta_dist > 0:
                            # 配速 = 时间/距离，单位 sec/km
                            pace_s_per_km = delta_s / (delta_dist / 1000)
                            # 过滤异常配速值（超过 20 分钟/公里或小于 2 分钟/公里）
                            if pace_s_per_km < 1200 and pace_s_per_km > 120:
                                pace_min = int(pace_s_per_km // 60)
                                pace_sec = int(pace_s_per_km % 60)
                                pace_series.append({
                                    "time": time_str,
                                    "elapsed": elapsed_s,
                                    "pace": pace_s_per_km,
                                    "pace_str": f"{pace_min}:{pace_sec:02d}"
                                })
                    except Exception:
                        pass

        return {
            "filename": filename,
            "sport": sport_name,
            "date": display_date,
            "points": points_added,
            "distance": watch_total_dist,
            "duration": watch_total_time_s,
            "avg_hr": summary_hr,
            "avg_cadence": summary_cadence,
            "calories": activity.get('totalCalories', 0) / 1000.0,
            "path": overview_path,
            "hr_series": hr_series,
            "pace_series": pace_series
        }
    return None

def parse_huawei_zip(zip_path, password, output_dir, start_date=None, end_date=None, progress_callback=None):
    """
    流式解析华为 ZIP 文件，边解压边处理，避免一次性加载全部数据到内存。
    进度反馈包含两个阶段：文件解析阶段 + 活动处理阶段
    """
    os.makedirs(output_dir, exist_ok=True)
    password_bytes = password.encode('utf-8')

    start_ts, end_ts = None, None
    if start_date:
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    if end_date:
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc).timestamp() * 1000)

    results = []

    try:
        with pyzipper.AESZipFile(zip_path, 'r', compression=pyzipper.ZIP_LZMA, encryption=pyzipper.WZ_AES) as z:
            # 第一阶段：快速扫描获取 JSON 文件列表（不读取内容）
            json_files = []
            for name in z.namelist():
                if name.startswith('Motion path detail data & description/motion path detail data') and name.endswith('.json') and 'Description' not in name:
                    if name.endswith('motion path detail data.json'):
                        continue
                    json_files.append(name)

            total_files = len(json_files)
            if total_files == 0:
                return []

            # 第二阶段：流式处理 - 逐个读取并立即提交处理
            processed_files = 0
            total_activities = 0
            completed_activities = 0

            # 使用线程池并行处理活动
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                pending_futures = []

                for json_file in json_files:
                    processed_files += 1

                    # 更新进度：显示文件解析阶段
                    if progress_callback:
                        progress_callback(
                            completed_activities,
                            total_activities if total_activities > 0 else processed_files,
                            f"解析文件 {processed_files}/{total_files}"
                        )

                    # 读取并解析单个 JSON 文件
                    try:
                        with z.open(json_file, pwd=password_bytes) as f:
                            content_bytes = f.read(MAX_JSON_SIZE + 1)
                            if len(content_bytes) > MAX_JSON_SIZE:
                                raise ValueError("JSON entry is too large")
                            content = content_bytes.decode('utf-8', errors='ignore')
                            fixed_content = fix_json_content(content)
                            activities = json.loads(fixed_content)
                            if not isinstance(activities, list):
                                raise ValueError("Activity JSON must contain an array")

                            # 更新总数并立即提交处理
                            total_activities += len(activities)
                            for act in activities:
                                future = executor.submit(
                                    process_single_activity,
                                    act, start_ts, end_ts, output_dir
                                )
                                pending_futures.append(future)

                    except Exception:
                        continue

                    # 定期检查已完成的任务，释放内存
                    # 每处理 5 个文件后检查一次
                    if processed_files % 5 == 0:
                        for future in concurrent.futures.as_completed(pending_futures):
                            try:
                                res = future.result()
                            except Exception:
                                res = None
                            completed_activities += 1
                            if res:
                                results.append(res)
                                if progress_callback:
                                    progress_callback(
                                        completed_activities,
                                        total_activities,
                                        res.get("sport", "")
                                    )
                            elif progress_callback and completed_activities <= total_activities:
                                progress_callback(completed_activities, total_activities, "")
                        # 清空已完成的 futures 列表
                        pending_futures = []

                # 第三阶段：处理剩余的任务
                for future in concurrent.futures.as_completed(pending_futures):
                    try:
                        res = future.result()
                    except Exception:
                        res = None
                    completed_activities += 1
                    if res:
                        results.append(res)
                        if progress_callback:
                            progress_callback(
                                completed_activities,
                                total_activities,
                                res.get("sport", "")
                            )
                    elif progress_callback and completed_activities <= total_activities:
                        progress_callback(completed_activities, total_activities, "")

    except pyzipper.zipfile.BadZipFile:
        raise RuntimeError("Invalid ZIP file or corrupted archive.")
    except RuntimeError as e:
        if 'Bad password' in str(e) or 'password' in str(e).lower():
            raise RuntimeError("Incorrect extraction password provided.")
        raise e
    except Exception as e:
        if 'Bad password' in str(e):
            raise RuntimeError("Incorrect extraction password provided.")
        raise e

    results.sort(key=lambda x: x['date'], reverse=True)
    return results

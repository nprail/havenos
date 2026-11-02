#!/usr/bin/env bash
# Sample total RSS + CPU of a process tree (used for the Pi measurements).
# usage: scripts/measure.sh <python3|pattern> [seconds=60] [interval=2]
#   havenOS: scripts/measure.sh "python -m havenos" 120
# Prints CSV: t_sec,rss_mb,cpu_pct  and a summary (avg/max). Also prints SoC temp if available.
set -euo pipefail
PAT="${1:?process pattern}"; DUR="${2:-60}"; INT="${3:-2}"
echo "t_sec,rss_mb,cpu_pct,soc_temp_c"
end=$((SECONDS + DUR)); t0=$SECONDS
rows=()
while [ $SECONDS -lt $end ]; do
  # all matching processes (pgrep -f matches full command line, so child processes are included)
  pids=$(pgrep -f -- "$PAT" | tr '\n' ',' | sed 's/,$//')
  if [ -n "$pids" ]; then
    read -r rss cpu < <(ps -o rss=,pcpu= -p "$pids" | awk '{r+=$1; c+=$2} END {printf "%.0f %.1f\n", r/1024, c}')
  else
    rss=0; cpu=0
  fi
  temp=""
  [ -r /sys/class/thermal/thermal_zone0/temp ] && temp=$(awk '{printf "%.1f", $1/1000}' /sys/class/thermal/thermal_zone0/temp)
  line="$((SECONDS - t0)),$rss,$cpu,$temp"
  echo "$line"; rows+=("$line")
  sleep "$INT"
done
printf '%s\n' "${rows[@]}" | awk -F, '
  {n++; r+=$2; c+=$3; if($2>mr)mr=$2; if($3>mc)mc=$3}
  END {if(n) printf "\nsummary: samples=%d  rss avg=%.0f MB max=%.0f MB  cpu avg=%.1f%% max=%.1f%% (100%% = one core)\n", n, r/n, mr, c/n, mc}'

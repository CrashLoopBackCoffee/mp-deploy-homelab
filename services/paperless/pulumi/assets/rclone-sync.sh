#!/bin/sh
mkdir -p {{ rclone_config_dir_write }}
cat {{ rclone_config_dir_readonly }}/{{ rclone_config_file_name }} > {{ rclone_config_dir_write }}/{{ rclone_config_file_name }}

while true; do
  echo "$(date --iso-8601=seconds) *********************************************************************************************"
  set -x
{%- for destination in destinations %}
  rclone sync {{ rclone_media_mount }}/documents/originals {{ destination }} --config {{ rclone_config_dir_write }}/{{ rclone_config_file_name }} -v
{%- endfor %}
  set +x
  sleep {{ sync_period_sec }}
done

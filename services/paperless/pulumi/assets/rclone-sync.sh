#!/bin/sh
mkdir -p {{ rclone_config_dir_write }}
cat {{ rclone_config_dir_readonly }}/{{ rclone_config_file_name }} > {{ rclone_config_dir_write }}/{{ rclone_config_file_name }}

while true; do
  echo *********************************************************************************************
  set -x
  rclone sync {{ rclone_media_mount }}/documents/originals {{ destination }} --config {{ rclone_config_dir_write }}/{{ rclone_config_file_name }} -v
  set +x
  sleep {{ sync_period_sec }}
done

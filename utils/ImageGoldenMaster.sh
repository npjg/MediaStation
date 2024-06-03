#!/usr/bin/env bash

set -e

# READ THE COMMAND-LINE ARGUMENTS.
cdrom_device=$1
index=$2

# READ THE CD TOC
cdrdao read-toc --device "$cdrom_device" "$index.toc"

# CREATE AN ISO IMAGE.
ddrescue -b 2048 -r1 -v "$cdrom_device" "$index.iso" "$index.log"

# MOUNT THE PC PART OF THE ISO.
echo "*** WINDOWS PARTITION ***"
mount_point=$(mktemp -d)
sudo mount "$index.iso" "$mount_point"
ls -la "$mount_point"
sudo umount "$mount_point"
rmdir "$mount_point"

echo 
echo "*** MAC PARTITION ***"
hmount "$index.iso"
hls
humount

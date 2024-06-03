#!/usr/bin/env bash

# DEFINE ERROR HANDLERS.
set -e 
# Since we have set -e, any errors will cause the script to exit immediately,
# so we must trap EXIT instead. 
trap cleanup EXIT
cleanup() {
    echo -e "\nAttempting to clean up mount points and attached disks..."
    # We don't want to show any more errors.
    umount "$mount_point"
    rmdir "$mount_point"
    diskutil eject "$disk_identifier"
}

# TODO: Verify the command line arguments and provide usage.

# STORE THE PATHS.
iso_path="$1"
mount_point="$(mktemp -d)"
cwd="$(pwd)"

# ATTACH THE DISK IMAGE.
# When a disk image contains an HFS volume, the disk must
# be attached and THEN mounted, which is just a fluke of 
# newer Macs I guess.
#
# When a partition is successfully attached,
# `hdiutil` returns output like the following:
# /dev/disk4          	Apple_partition_scheme         	
# /dev/disk4s1        	Apple_partition_map            	
# /dev/disk4s2        	ISO                            	
# /dev/disk4s3        	Apple_HFS    
# 
# The "ISO" line corresponds to the PC filesystem, and the
# Apple_HFS corresponds (of course) to the HFS volume.  
partitions_on_attached_iso=$(hdiutil attach -nomount "$iso_path")
echo $partitions_on_attached_iso

# MOUNT THE WINDOWS (CD9660) PORTION.
disk_identifier=$(echo "$partitions_on_attached_iso" | awk '{print $1}' | head -n 1)
echo "CD9660 Portion: $mount_point"
mount -t cd9660 "$disk_identifier" "$mount_point"

# PRINT THE HASHES OF EACH FILE IN THE WINDODWS PORTION.
# This gets the hashes of all files in the root directory.
for file in "$mount_point"/*; do 
    md5sum "$file" 2> /dev/null
done | grep -v "Not a regular file" | sed "s|$mount_point/||" | awk '{ print $2, $1 }'
# This gets the hashes of all files in subdirectories.
for file in "$mount_point"/**/**; do 
    md5sum "$file" 2> /dev/null
done | grep -v "Not a regular file" | sed "s|$mount_point/||" | awk '{ print $2, $1 }'

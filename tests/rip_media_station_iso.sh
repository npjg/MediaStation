#! bash

# This script rips a Media Station ISO to a directory whose name should uniquely
# identify the edition of the title in a human-readable fashion. It is designed to
# help with cataloging the many Media Station titles that are out there to create 
# a test dataset.
#
# In addition, mounting hybrid Windows/HFS CD-ROM images is difficult on modern
# macOS, as even the Windows portion will just refuse to mount with the typical
# double-click. This script encapsulates the complexity required to mount these
# hybrid CD-ROMs on macOS.
#
# To access HFS volumes, `hfstools` MUST be installed.

# DEFINE ERROR HANDLERS.
set -e 
# Since we have set -e, any errors will cause the script to exit immediately,
# so we must trap EXIT instead. 
trap cleanup EXIT
cleanup() {
        echo -e "\nAttempting to clean up mount points and attached disks..."
        # We don't want to show any more errors.
        umount "$mount_point" > /dev/null || true
        rmdir "$mount_point" > /dev/null
        humount > /dev/null
        diskutil eject "$disk_identifier" > /dev/null
}

# TODO: Verify the command line arguments and provide usage.

# STORE THE PATHS.
iso_path="$1"
script_directory="$(dirname "$(readlink -f "$0")")"
extracted_files_root="$script_directory/test_data/Extracted Folders"
ISOS_ROOT="$script_directory/test_data/ISOs"
mount_point="$(mktemp -d)"

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

# GET BASIC INFO ABOUT THE TITLE.
# Get the info from BOOT.STM. This also serves as a basic sanity
# check that we are examining a Media Station title, as the BOOT.STM
# should always be present.
echo "BOOT.STM"
bootstm_path=$(find "$mount_point" -iname "boot.stm" -print)
if [ -z "$bootstm_path" ]; then
  echo "Error: BOOT.STM not found on CD-ROM. This is likely not a Media Sation title, or it uses some format we're not aware of yet."
  exit 1
elif [ $(echo "$bootstm_path" | wc -l) -gt 1 ]; then
  echo "Warning: Multiple BOOT.STMs found: $bootstm_path. Using the first one."
  bootstm_path=$(echo "$bootstm_path" | head -n 1)
fi
xxd -l 256 "$bootstm_path"

# Get the info from PROFILE._ST.
echo "PROFILE._ST"
profilest_path=$(find "$mount_point" -iname "profile._st" -print)
if [ -z "$profilest_path" ]; then 
  echo "No profile._st found."
else
  if [ $(echo "$profilest_path" | wc -l) -gt 1 ]; then
    echo "Warning: Multiple PROFILE._STs found: $profilest_path. Using the first one."
    profilest_path=$(echo "$profilest_path" | head -n 1)
  fi
  xxd -l 256 "$profilest_path"
fi

# Get the info from the game EXE.
# (This is the version number reported in the About screen.)
# I thought this would report the correct size, 
echo "EXEs"
for exe in $(find "$mount_point" -iname "*.exe" -print); do
    echo " $exe"
    # First we will search for just ASCII strings.
    strings $exe | grep -E ".+/[A-Z][A-Z]$" || true
    # Then we will search for little-endian UTF-8 string.
    # Sadly, even with the latest from binutils, we still
    # need to run it separately.
    strings -e l $exe  | grep -E ".+/[A-Z][A-Z]$" || true
done

# COPY THE PC PORTION TO THE CORRECT DIRECTORY.
#  - Game Title (DW, Dalmatians, etc.)
#  - Title Compiler Version from BOOT.STM (4.0r8, T3.5r5, etc.) 
#  - Engine Version from player EXE (2.0/GB, 1.0/US, etc.)
#  - Platform (Windows, Mac) from PROFILE._ST
#  - Language (English, German, etc.)
#    This cannot always be reliably deduced from the Engine Version.
read -p "Game Title: " game_name
read -p "Title Compiler Version (e.g. 4.0r8): " title_compiler_version
read -p "Engine Version (e.g. 1.0/US): " engine_version
read -p "Language: " language
platform="Windows"
folder_name="$game_name - $title_compiler_version - $engine_version - $language - $platform"
pc_folder_path="$extracted_files_root/$folder_name"
if [ ! -d "$pc_folder_path" ]; then
  mkdir -p "$pc_folder_path"
else
  echo "Directory already exists and will not be overwritten: $pc_folder_path"
  exit 1
fi

cp -rv "$mount_point"/* "$pc_folder_path"
umount "$mount_point"
rmdir "$mount_point"

# MOUNT THE HFS (Macintosh) PORTION.
# TODO: Make sure there is indeed an HFS portion.
echo -e "\nAttempting to mount HFS (Macintosh) portion with hmount..."
hfs_partition=$(echo "$partitions_on_attached_iso" | grep "Apple_HFS" | awk '{print $1}')
if [ -n "$hfs_partition" ]; then
  hmount $hfs_partition

  # COPY THE MAC PORTION TO THE CORRECT DIRECTORY.
  # We will assume that the versions are all the same as the PC one... though maybe this should be checked.
  # It is easier to just check the PC version since hfstools doesn't provide direct access to the files; they
  # must be copied out first.
  platform="Mac"
  folder_name="$game_name - $title_compiler_version - $engine_version - $language - $platform"
  mac_folder_path="$extracted_files_root/$folder_name"
  mkdir -p "$mac_folder_path"
  # These files just have a data fork. Executable files need to have a resource fork copied to to be useful.
  # This is not a recursive copy but specifying that we want raw data (just the data fork).
  echo "Copying data from HFS volume to $mac_folder_path (progress will not echo)..."
  # Apparently you cannot use the path 'data/*' to get the paths.
  # TODO: For DW and maybe some others, the CXTs aren't in a data directory, they
  # are in program/data directory, so you might need to change to that.
  # hcd program
  hcd data
  hcopy -r '*' "$mac_folder_path"
  humount

  # CHECK THE HASHES.
  # The hashes of the data files should be EXACTLY the same across the Windows and Mac versions.
  # The only difference should be the executable file, of course.
  echo -e "\nChecking to see if there is any difference in the data files in the Windows and Mac versions..."
  echo "If there is a difference a diff will be shown here."
  pc_hashes=$(mktemp)
  echo "Windows hashes stored at $pc_hashes"
  # md5sum returns lines like this:
  #  b74d5f875eff726d2a1b7c0778ffd769  ./DATA/160.CXT
  # This extracts the first field (hash). The filenames might have different capitalization
  # and so forth, so rather than worrying about that we will just sort in place and then check
  # the hash list. Of course, if they don't match then there will be some more effort to sort out
  # which lines don't match. 
  find "$pc_folder_path" \( -iname "*.cxt" -o -iname "*.stm" -o -iname "*._st" \) -exec md5sum {} + | sort | awk '{print $1}' > $pc_hashes
  mac_hashes=$(mktemp)
  echo "Mac hashes stored at $mac_hashes"
  find "$mac_folder_path" \( -iname "*.cxt" -o -iname "*.stm" -o -iname "*._st" \) -exec md5sum {} + | sort | awk '{print $1}' > $mac_hashes
  set +e
  windows_mac_hash_diff=$(diff $pc_hashes $mac_hashes)
  set -e
  echo $windows_mac_hash_diff
  if [ -z "$windows_mac_hash_diff" ]; then
    echo "Hashes match exactly, so removing the Mac version..."
    rm -r "$mac_folder_path"
  fi
  # rm $pc_hashes $mac_hashes
else
  echo "No HFS partition found, so skipping Mac portion."
fi

# DETATCH THE DISK IMAGE.
echo -e "\nMoving ISO to the correct location..."
diskutil eject "$disk_identifier"

# MOVE THE ISO TO MATCH THE NAME.
# Since the ISO has both platforms, we don't need to include the platform.
# This could be a little bit less descriptive than possible if there is just
# one platform in the image (like George Shrinks, which is Windows only), but
# that is okay for now.
iso_filename="$game_name - $title_compiler_version - $engine_version - $language.iso"
new_iso_path="$ISOS_ROOT/$iso_filename"
mv -v "$iso_path" "$new_iso_path"

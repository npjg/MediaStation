
from typing import List

from asset_extraction_framework.Asserts import assert_equal
from asset_extraction_framework.File import File

TEXT_ENCODING = 'latin-1'
SECTION_SEPARATOR = '!'
# At the end of several sections, we see "summary" notation like the following:
#  * 3987 20432 3881 15000
# This has been observed for the following sections:
#  - Asset declarations
#    Example (101 Dalmatians):
#      sound_6cp2_GoodByeForNow 3663 3877
#      image_6cp2_background 3653 3878
#      * 3987 20432 3881 15000
#
#  - Context declarations 
#    Example (101 Dalmatians):
#      "1527.cxt" 127
#      "126.cxt" 128
#      * 130
#
#  - Variable declarations
#    Example (101 Dalmatians):
#       v_6cX6_comingFromLibrary 1207
#       var_6c09_bool_OpeningPlayed 1576
#       * 1687
#
#  - Resource declarations
#    Example (101 Dalmatians):
#       $upArrow 10037
#       $downArrow 10038
#       * 10039
#
# I am not sure what these numbers mean yet. Sometimes it looks like they're the
# maximum ID for whatever type we're looking at in the title, but sometimes this
# also doesn't seem to be the case. So further investigation is necessary!
SUMMARY_INDICATOR = '*'

class Profile(File):
    ## Reads a profile from the given location. Profiles contain the names and IDs of all
    ## the assets in this title, along with other data. For newer titles, the asset names
    ## are contained in the Contexts themselves, but for older titles the asset names
    ## are ONLY contained in this file. The extractor can read the asset names in the 
    ## profile to assign better names to the exported assets.
    ## \param[in] - filepath: The filepath of the file, if it exists on the filesystem.
    ##                        Defaults to None if not provided.
    ## \param[in] - stream: A BytesIO-like object that holds the file data, if the file does
    ##                      not exist on the filesystem.
    ## NOTE: It is an error to provide both a filepath and a stream, as the source of the data
    ##       is then ambiguous.
    def __init__(self, filepath: str = None, stream = None):
        # OPEN THE FILE FOR READING.
        # We need to open the file in text-reading mode so the newlines are automatically handled.
        super().__init__(filepath = filepath, stream = stream)
        lines_in_file = self.readline_with_universal_newline(self.stream)
        # In all title versions tested thus far, all these sections are present
        # in this order.
        self.version = Version(lines_in_file)
        self.contexts = ProfileSection(lines_in_file, ContextDeclaration)
        self.asset_declarations = ProfileSection(lines_in_file, AssetDeclaration)
        self.file = ProfileSection(lines_in_file, FileDeclaration)
        self.variables = ProfileSection(lines_in_file, VariableDeclaration)
        self.resources = ProfileSection(lines_in_file, ResourceDeclaration)
        self.constants = ProfileSection(lines_in_file, ConstantDeclaration)

    # The File class was designed for binary files, not text files.
    # Some implementation details of the File class thus sadly bypass the 
    # default universal readline support with stream.readline(). 
    #
    # Specifically, the mmap.mmap stream that the binary data is wrapped in
    # only seems to recognize \n as a line separator, but not \r by itself.
    # That means Profiles from Mac versions will not be read correctly;
    # the file appears as one huge line. 
    #
    # So this generator restores "universal" newline functionality to mmap.mmap
    # streams.
    def readline_with_universal_newline(self, stream):
        raw_data = stream.read()
        split_by_carriage_return = raw_data.split(b'\r')
        for line in split_by_carriage_return:
            # This strips out any other whitespace (including a newline)
            # from the line, leaving good clean data!
            yield line.strip()

class ProfileSection:
    ## Creates a profile section that contains entries (parsed forms of individual
    ## lines of text from the Profile file). 
    ## \param[in] lines_in_file - The generator to get the lines from the Profile file.
    ## \param[in] profile_entry_class - The class that should be used to create profile
    ##            entries from each line of text.
    def __init__(self, lines_in_file, profile_entry_class):
        self.entries = []
        for line in lines_in_file:
            # READ THIS ENTRY.
            entry = profile_entry_class(line)
            if entry._end_of_section:
                break

            # STORE THIS ENTRY.
            if not entry._is_summary:
                # This is a regular record (far more common, so
                # it's listed first).
                self.entries.append(entry)
            else:
                # The "summary" section must be stored separately.
                # I don't yet know how to interpret it.
                self.summary = entry

class ProfileEntry:
    ## Creates a profile entry from the given line of text from the Profile file.
    ## \param[in] line - A binary string containing the lined from the Profile
    ##            file that should be put into the Profile entry.
    def __init__(self, line: bytes):
        self._raw_entry: List[str] = line.strip().decode(TEXT_ENCODING).split(' ')
        # Check if this is a summary entry (see above).
        if self._raw_entry[0] == SUMMARY_INDICATOR:
            self._is_summary = True
        else:
            self._is_summary = False
        # Check if this is the end of the section.
        if self._raw_entry == [SECTION_SEPARATOR]:
            self._end_of_section = True
        else:
            self._end_of_section = False

## Examples:
##  _Version3.4_ _PC_
##  _Version3.3_ _MAC_
class Version(ProfileEntry):
    def __init__(self, lines_in_file):
        line = next(lines_in_file)
        super().__init__(line)
        if self._end_of_section:
            return

        self.version_number: str = self._raw_entry[0]
        # Known strings are "PC" and "MAC".
        self.platform: str = self._raw_entry[1]

        # PRINT THIS INFORMATION FOR DEBUGGING PURPOSES.
        print(f'---\n {self.version_number} {self.platform}\n---')

## Examples:
##  Context cxt_7x70_Sounds 888886792
##  ^       ^               ^
##  type    name            unk1
##
##  Screen scr_7x81 889300178
##  ^      ^        ^
##  type   name    unk1
class ContextDeclaration(ProfileEntry):
    def __init__(self, lines_in_file):
        super().__init__(lines_in_file)
        if (self._is_summary) or (self._end_of_section):
            return
        # Known type strings are "Document", "Context", and "Screen".
        self.type: str = self._raw_entry[0]
        self.name: str = self._raw_entry[1]
        self.unk1: int = int(self._raw_entry[2])

## Examples:
##  Root_7x00 109 0
##  ^         ^   ^ -----
##  name      asset_id  |
##                      chunk_id (none)
##
##  img_7x00gg011all_RadioLines 162 8
##  ^                           ^   ^ -----
##  name                        asset_id  |
##                                        chunk_id (a008)
##
##  mov_7xb2_MSIBumper 265 104 105 106
##  ^                  ^   ^---^---^--
##  name               asset_id  |
##                               chunk_ids (a068, a069, a06a)
class AssetDeclaration(ProfileEntry):
    def __init__(self, lines_in_file):
        super().__init__(lines_in_file)
        self._chunk_ids = []
        if (self._is_summary) or (self._end_of_section):
            return

        # READ THE ASSET NAME.
        # Later titles have asset names built right into the asset headers, 
        # but earlier titles only map the asset names to asset IDs in PROFILE._ST.
        self.name: str = self._raw_entry[0]

        # CHECK IF WE HAVE AN IMAGE SET.
        # In Hercules, there is a puzzling line in PROFILE._ST:
        #  "# image_7d12g_Background 15000 15001 15002 15003 15004 15005 15006 15007 15008 15009 15010 15011 15012 15013"
        # This line calls out all the IDs of the bitmap set. These IDs are not really asset IDs, but some other IDs.
        # It isn't really necessary to process this line becuase the image set has its own asset ID. 
        # 
        # In the case of Hercules, it's in the immediately previous line:
        #  "image_7d12g_Background 1453 254"
        # Since there is no unique name assigned to each of the bitmaps in the bitmap set (only the IDs noted above),
        # we will just discard this line.
        IMAGE_SET_LINE_INDICATOR = '#'
        if (IMAGE_SET_LINE_INDICATOR == self.name):
            print(f'INFO: Found image set: {self._raw_entry}. This case might not be completely handled yet.')
            self._is_summary = True
            return

        self.id: int = int(self._raw_entry[1])
        # Movies have more than one chunk, so we will just get the rest of the line.
        # TODO: Verify exactly three are actually listed.
        raw_chunk_ids = self._raw_entry[2:]
        self._chunk_ids = [int(raw_chunk_id) for raw_chunk_id in raw_chunk_ids]

    @property
    def _has_associated_chunks(self):
        # The presence of no chunks is indicated by a chunk ID of 0.
        if len(self._chunk_ids) == 0 or (self._chunk_ids[0] == 0):
            return False
        else:
            return True

    ## \return A list of FourCCs associated with this asset, if there are any.
    ##         If there are no chunks for this asset, None is returned.
    ## The FourCC is generated by converting each chunk ID to a one-bsaed, 3-digit 
    ## hex number and appending an "a".
    ## For the three examples provided above, these would be returned:
    ##  Root_7x00 109 0                    -> None
    ##  img_7x00gg011all_RadioLines 162 8  -> ['a008']
    ##  mov_7xb2_MSIBumper 265 104 105 106 -> ['a068', 'a069', 'a6a']
    @property
    def four_ccs(self):
        if not self._has_associated_chunks:
            return None
        
        def create_fourcc(chunk_id: int) -> str:
            if chunk_id > 0xfff:
                raise ValueError(f'Chunk ID {chunk_id} too large to fit in 4-character FourCC.')
            return f'a{chunk_id:03x}'
        return [create_fourcc(chunk_id) for chunk_id in self._chunk_ids]

## Examples:
##  "3664.cxt" 100
##  ^          ^
##  filename   file_id
##
##  "113.cxt" 101
##  ^         ^
##  filename  file_id
##
##  "436.cxt" 102
##  ^         ^
##  filename  file_id
class FileDeclaration(ProfileEntry):
    def __init__(self, lines_in_file):
        super().__init__(lines_in_file)
        if (self._is_summary) or (self._end_of_section):
            return

        self.filename: str = self._raw_entry[0]
        self.file_id: int = int(self._raw_entry[1])

## Examples:
##  var_6c00_01_CurrentThesaurusImage 100
##  ^                                 ^
##  variable_name                     variable_id
##
##  var_6c00_01_CurrentThesaurusSound 101
##  ^                                 ^
##  variable_name                     variable_id
##
##  var_6c00_01_CurrentThesaurusMovie 102
##  ^                                 ^
##  variable_name                     variable_id
class VariableDeclaration(ProfileEntry):
    def __init__(self, lines_in_file):
        super().__init__(lines_in_file)
        if (self._is_summary) or (self._end_of_section):
            return

        self.variable_name: str = self._raw_entry[0]
        self.variable_id: int = int(self._raw_entry[1])

## Examples:
##  $Yes 10000
##  $resource 10001
##  $Deactivate 10002
class ResourceDeclaration(ProfileEntry):
    def __init__(self, lines_in_file):
        super().__init__(lines_in_file)
        if (self._is_summary) or (self._end_of_section):
            return

        self.resource_name: str = self._raw_entry[0]
        self.resource_id: int = int(self._raw_entry[1])

## Examples:
##  SCREENCOVER_Z -100
##  KNS_COVER_Z -100
##  PLAY_BACKGROUND_PATCH 00:29.00
class ConstantDeclaration(ProfileEntry):
    def __init__(self, lines_in_file):
        super().__init__(lines_in_file)
        if (self._is_summary) or (self._end_of_section):
            return

        self.constant_name: str = self._raw_entry[0]
        self.constant_value = None
        if len(self._raw_entry) > 1:
            self.constant_value = self._raw_entry[1]
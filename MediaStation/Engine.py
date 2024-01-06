#! python3

## This program extracts asets from Media Station titles. Refer to the readme 
## for information on tested titles and known issues.
## Overall Design:
##  - Some of the data structures used in the files are rather strange and suited 
##    for real-time playback instead of asset extraction. So first all the data is
##    read from the files. Each structure in the data files generally has its own
##    class in this application, and structures that correspond to multimedia assets 
##    also support exporting. There is a little bit of inconsistency as to what
##    constitutes a "structure" here as opposed to just a piece of another structure.
##    But the arrangement I have adopted has seemed to preserve conceptual integrity 
##    pretty well.
##  - Each of the classes populated from the data is generally exported to JSON.
##  - Multimedia files are exported to BMP or WAV.

from typing import List

from asset_extraction_framework.CommandLine import CommandLineArguments
from asset_extraction_framework.Application import Application, FileDetectionEntry

from MediaStation import global_variables 
from MediaStation.System import System
from MediaStation.Context import Context
from MediaStation.Profile import Profile

class MediaStationEngine(Application):
    def __init__(self, application_name: str):
        super().__init__(application_name)

    ## Verifies that the asstes listed in the BOOT.STM file are exactly the ones
    ## that are actually present in the CXT files.
    def check_integrity(self):
        pass

    def get_context_by_file_id(self, file_id):
        for file in self.files:
            if isinstance(file, Context):
                if file.parameters.file_number == file_id:
                    return file

    ## Gets an asset with associated data chunk(s) by the FourCC for those chunk(s).
    ## Usually assets are defined in the same context that has their data, so this 
    ## is not necessary. However, some new-generation titles have INSTALL.CXT files,
    ## intended to be copied to the hard drive, that only contain asset data chunks
    ## and no asset headers. So this application-level lookup is necessary to correctly
    ## link up the data in this file with the asset headers.
    def get_asset_by_chunk_id(self, chunk_id: str):
        for file in self.files:
            if isinstance(file, Context):
                found_asset = file.get_asset_by_chunk_id(chunk_id)
                if found_asset is not None:
                    return found_asset

    ## \return The asset whose asset ID matches the provided asset ID.
    ## If no asset in any of the parsed files matches, None is returned.
    def get_asset_by_asset_id(self, asset_id: int):
        for file in self.files:
            if isinstance(file, Context):
                found_asset = file.get_asset_by_asset_id(asset_id)
                if found_asset is not None:
                    return found_asset

    # Uses the mapping in PROFILE._ST to correlate the numeric asset IDs
    # to descriptive asset names. Later titles had the asset names encoded
    # directly in the asset headers, in which case this isn't necessary.
    # But for earlier titles, the only way to get the names is to read
    # the PROFILE._ST as is done here.
    def correlate_asset_ids_to_names(self):
        # FIND THE PROFILE.
        # TODO: Verify there is at most ONE profile.
        profile = None
        for file in self.files:
            if isinstance(file, Profile):
                profile = file

        # MAKE SURE THERE IS A PROFILE.
        if profile is None:
            # Some early titles (like Lion King) don't have a PROFILE._ST,
            # so we're out of luck with finding asset names. Maybe if the 
            # original sources can be found one day, we would know that 
            # information, but it isn't available on the CD-ROMS.
            return
        
        for asset_entry in profile.asset_declarations.entries:
            corresponding_asset = self.get_asset_by_asset_id(asset_entry.id)
            if corresponding_asset is not None:
                # VERIFY THERE IS NO ASSET NAME CONFLICT.
                # In later titles that encode the asset name in the asset header and 
                # also put the asset names in PROFILE._ST, there could be an inconsistency
                # between the two. We will check to ensure this isn't the case.
                if corresponding_asset.name is not None:
                    if corresponding_asset.name != asset_entry.name:
                        print(f'WARNING: Asset names disagree. Name in asset: {corresponding_asset.name}. Name in PROFILE._ST: {asset_entry.name}.')
                        continue
                
                corresponding_asset.name = asset_entry.name
                continue
            
            # CHECK IF THE ENTRY CORRESPONDS TO A CONTEXT.
            # Contexts have assigned asset IDs too, as in this example:
            #  "context_7d07g_PurplePurpleNo 1000 0"
            # In this script, assets currently are not stored in the
            # asset headers list because asset headers are not provided for contexts,
            # at least not in the same way.
            corresponding_context = self.get_context_by_file_id(asset_entry.id)
            if corresponding_context is not None:
                corresponding_context.parameters.name = asset_entry.name
                continue
            
            print(f'WARNING: Asset {asset_entry.id} present in PROFILE._ST but not found in parsed assets.')

def main(raw_command_line: List[str] = None):
    # DEFINE THE FILE TYPES IN THIS APPLICATION.
    file_detection_entries = [
        # We want to process the BOOT.STM and PROFILE._ST (if present) becuase these both provide useful debugging
        # information that we want to show to the user first thing.
        FileDetectionEntry(filename_regex = '.*\.stm$', case_sensitive = False, file_processor = System),
        FileDetectionEntry(filename_regex = 'profile._st$', case_sensitive = False, file_processor = Profile),
        # All regular context files have only digits in their main file names. 
        FileDetectionEntry(filename_regex = '\d+\.cxt$', case_sensitive = False, file_processor = Context),
        # The INSTALL.CXT, if present, MUST be read after all the other contexts are read. This is because 
        # INSTALL.CXT contains no asset headers; it jumps directly into the asset subfiles. So if the asset
        # headers have not all been read, an error will be thrown. It is much simpler to just force INSTALL.CXT
        # to be read afterward than let asset subfiles be read before the headers.
        FileDetectionEntry(filename_regex = 'install.cxt$', case_sensitive = False, file_processor = Context),
    ]

    # PARSE THE COMMAND-LINE ARGUMENTS.
    APPLICATION_NAME = 'Media Station'
    APPLICATION_DESCRIPTION = ''
    command_line_arguments = CommandLineArguments(APPLICATION_NAME, APPLICATION_DESCRIPTION).parse(raw_command_line)

    # PARSE THE ASSETS.
    media_station_engine = MediaStationEngine(APPLICATION_NAME)
    global_variables.application = media_station_engine
    # TODO: Display a scary warning if individual files are passed in.
    media_station_engine.process(command_line_arguments.input, file_detection_entries)
    media_station_engine.correlate_asset_ids_to_names()

    # EXPORT THE ASSETS, IF REQUESTED.
    if command_line_arguments.export:
        media_station_engine.export(command_line_arguments)

# TODO: Get good documentation here.
if __name__ == '__main__':
    main()
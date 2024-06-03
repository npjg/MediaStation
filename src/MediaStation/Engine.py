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
import os

from asset_extraction_framework.CommandLine import CommandLineArguments
from asset_extraction_framework.Application import Application

from MediaStation import global_variables 
from MediaStation.System import System, FileDeclaration
from MediaStation.Context import Context
from MediaStation.Profile import Profile

class MediaStationEngine(Application):
    def __init__(self, application_name: str):
        super().__init__(application_name)

    def get_context_by_file_id(self, file_id):
        for context in self.contexts:
            if context.parameters is not None:
                if context.parameters.file_number == file_id:
                    return context

    ## Gets an asset with associated data chunk(s) by the FourCC for those chunk(s).
    ## Usually assets are defined in the same context that has their data, so this 
    ## is not necessary. However, some new-generation titles have INSTALL.CXT files,
    ## intended to be copied to the hard drive, that only contain asset data chunks
    ## and no asset headers. So this application-level lookup is necessary to correctly
    ## link up the data in this file with the asset headers.
    def get_asset_by_chunk_id(self, chunk_id: str):
        for context in self.contexts:
            found_asset = context.get_asset_by_chunk_id(chunk_id)
            if found_asset is not None:
                return found_asset

    ## \return The asset whose asset ID matches the provided asset ID.
    ## If no asset in any of the parsed files matches, None is returned.
    def get_asset_by_asset_id(self, asset_id: int):
        for context in self.contexts:
            found_asset = context.get_asset_by_asset_id(asset_id)
            if found_asset is not None:
                return found_asset

    # Uses the mapping in PROFILE._ST to correlate the numeric asset IDs
    # to descriptive asset names. Later titles had the asset names encoded
    # directly in the asset headers, in which case this isn't necessary.
    # But for earlier titles, the only way to get the names is to read
    # the PROFILE._ST as is done here.
    def correlate_asset_ids_to_names(self):
        # MAKE SURE THERE IS A PROFILE.
        if self.profile is None:
            # Some early titles (like Lion King) don't have a PROFILE._ST,
            # so we're out of luck with finding asset names. Maybe if the 
            # original sources can be found one day, we would know that 
            # information, but it isn't available on the CD-ROMS.
            return
        
        for asset_entry in self.profile.asset_declarations.entries:
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
            
            print(f'WARNING: Asset {asset_entry.id} present in PROFILE._ST but not found in parsed assets: {asset_entry._raw_entry}')

    def process(self, input_paths):
        # READ THE STARTUP FILE (BOOT.STM).
        matched_boot_stm_files = self.find_matching_files(input_paths, r'boot\.stm$', case_sensitive = False)
        if len(matched_boot_stm_files) == 0:
            # TODO: I really wanted to support extracting individual CXTs, but 
            # I think that will be too complex and the potential use cases are
            # too small.
            print("ERROR: BOOT.STM is missing from the input path(s). This file contains vital information for processing Media Station games, and assets cannot be extracted without it. ")
            exit(1)
        if len(matched_boot_stm_files) > 1:
            print('ERROR: Found more than one BOOT.STM file in the given path(s). You are likely trying to process more than one Media Station title at once, which is not supported.')
            exit(1)
        system_filepath =  matched_boot_stm_files[0]
        print(f'INFO: Processing {system_filepath}')
        self.system = System(system_filepath)

        # READ THE MAIN CONTEXTS.
        matched_cxt_files = self.find_matching_files(input_paths, r'.*\.cxt$', case_sensitive = False)
        # And now we need to sort the CXTs based on what is in the system.
        # The INSTALL.CXT, if present, MUST be read after all the other contexts are read. This is because 
        # INSTALL.CXT contains no asset headers; it jumps directly into the asset subfiles. So if the asset
        # headers have not all been read, an error will be thrown. It is much simpler to just force INSTALL.CXT
        # to be read afterward than let asset subfiles be read before the headers.
        cdrom_context_filepaths = []
        other_context_filepaths = []
        for matched_cxt_filepath in matched_cxt_files:
            file_declaration_found = False
            for file_declaration in self.system.file_declarations:
                # Windows and Mac back in the day were case insensitive, so we must replicate that behavior.
                filenames_match = os.path.basename(matched_cxt_filepath).lower() == file_declaration.name.lower()
                if filenames_match:
                    file_declaration_found = True
                    if file_declaration.intended_location == FileDeclaration.IntendedFileLocation.CD_ROM:
                        cdrom_context_filepaths.append(matched_cxt_filepath)
                    else:
                        other_context_filepaths.append(matched_cxt_filepath)

            if not file_declaration_found:
                # This seems to legitimately happen for 1095.CXT and 1097.CXT in Lion King,
                # which are both only 16 bytes and don't appear at all in BOOT.STM
                # TODO: DOn't issue a warning for these files.
                print(f'WARNING: File declaration for {matched_cxt_filepath} not found in BOOT.STM. This file will not be processed or exported.')
        self.contexts: List[Context] = []
        for cxt_filepath in [*cdrom_context_filepaths, *other_context_filepaths]:
            print(f'INFO: Processing {cxt_filepath}')
            context = Context(cxt_filepath)
            self.contexts.append(context)

        # RESOLVE ASSET NAMES.
        matched_profile_st_files = self.find_matching_files(input_paths, r'profile\._st$', case_sensitive = False)
        self.profile = None
        if len(matched_profile_st_files) == 0:
            print('INFO: A PROFILE._ST is not available for this title, so nice-to-have information like asset names might not be available.')
        else:
            profile_filepath = matched_profile_st_files[0]
            print(f'INFO: Processing {profile_filepath}')
            self.profile = Profile(profile_filepath)
            self.correlate_asset_ids_to_names()

    def export_assets(self, command_line_arguments):
        application_export_subdirectory: str = os.path.join(command_line_arguments.export, self.application_name)
        for index, context in enumerate(self.contexts):
            print(f'INFO: Exporting assets in {context.filepath}')
            context.export_assets(application_export_subdirectory, command_line_arguments)

    # This is in a separate function becuase even on fast computers it 
    # can take a very long time and often isn't necessary.
    def export_metadata(self, command_line_arguments):
        application_export_subdirectory: str = os.path.join(command_line_arguments.export, self.application_name)

        print(f'INFO: Exporting metadata for {self.system.filename}')
        self.system.export_metadata(application_export_subdirectory)
        for context in self.contexts:
            print(f'INFO: Exporting metadata for {context.filename}')
            context.export_metadata(application_export_subdirectory)
        if self.profile is not None:
            print(f'INFO: Exporting metadata for {self.profile.filename}')
            self.profile.export_metadata(application_export_subdirectory)

def main(raw_command_line: List[str] = None):
    # PARSE THE COMMAND-LINE ARGUMENTS.
    APPLICATION_NAME = 'Media Station'
    APPLICATION_DESCRIPTION = ''
    command_line = CommandLineArguments(APPLICATION_NAME, APPLICATION_DESCRIPTION)
    command_line_arguments = command_line.parse(raw_command_line)

    # PARSE THE ASSETS.
    media_station_engine = MediaStationEngine(APPLICATION_NAME)
    global_variables.application = media_station_engine
    media_station_engine.process(command_line_arguments.input)

    # EXPORT THE ASSETS, IF REQUESTED.
    if command_line_arguments.export:
        media_station_engine.export_assets(command_line_arguments)
        media_station_engine.export_metadata(command_line_arguments)

# TODO: Get good documentation here.
if __name__ == '__main__':
    main()

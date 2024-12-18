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
import logging

from asset_extraction_framework.CommandLine import CommandLineArguments
from asset_extraction_framework.Application import Application

from MediaStation import global_variables 
from MediaStation.System import System, FileDeclaration
from MediaStation.Context import Context
from MediaStation.Profile import Profile

class MediaStationEngine(Application):
    def __init__(self, application_name: str):
        super().__init__(application_name)

        # CREATE THE LOGGER.
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

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
                        self.logger.warning(f'Asset names disagree. Name in asset: {corresponding_asset.name}. Name in PROFILE._ST: {asset_entry.name}.')
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
            
            self.logger.warning(f'Asset {asset_entry.id} present in PROFILE._ST but not found in parsed assets: {asset_entry._raw_entry}')

    def process(self, input_paths):
        # READ THE STARTUP FILE (BOOT.STM).
        matched_boot_stm_files = self.find_matching_files(input_paths, r'boot\.stm$', case_sensitive = False)
        if len(matched_boot_stm_files) == 0:
            # TODO: I really wanted to support extracting individual CXTs, but 
            # I think that will be too complex and the potential use cases are
            # too small.
            self.logger.error("BOOT.STM is missing from the input path(s). This file contains vital information for processing Media Station games, and assets cannot be extracted without it. ")
            exit(1)
        if len(matched_boot_stm_files) > 1:
            self.logger.error('Found more than one BOOT.STM file in the given path(s). You are likely trying to process more than one Media Station title at once, which is not supported.')
            exit(1)
        system_filepath =  matched_boot_stm_files[0]
        self.logger.info(f'Processing {system_filepath}')
        self.system = System(system_filepath)

        # READ THE PROFILE.
        self.profile = None
        matched_profile_st_files = self.find_matching_files(input_paths, r'profile\._st$', case_sensitive = False)
        if len(matched_profile_st_files) == 0:
            self.logger.info('A PROFILE._ST is not available for this title, so nice-to-have information like asset names might not be available.')
        else:
            profile_filepath = matched_profile_st_files[0]
            self.logger.info(f'Processing {profile_filepath}')
            try:
                self.profile = Profile(profile_filepath)
            except:
                self.logger.warning(f'An error occurred when parsing {profile_filepath}. Export will continue, but assets will not have names.')
                self.profile = None

        # READ THE MAIN CONTEXTS.
        # TODO: It really would be great to read one CXT and then export it,
        # rather than saving exporting to the end. That gives as much data as 
        # possible in the event of an error.
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
                # TODO: Don't issue a warning for these files.
                self.logger.warning(f'File declaration for {matched_cxt_filepath} not found in BOOT.STM. This file will not be processed or exported.')
        self.contexts: List[Context] = []
        for cxt_filepath in [*cdrom_context_filepaths, *other_context_filepaths]:
            self.logger.info(f'Processing {cxt_filepath}')
            context = Context(cxt_filepath)
            self.contexts.append(context)

        # RESOLVE ASSET NAMES.
        if self.profile is not None:
            self.correlate_asset_ids_to_names()

    def export_assets(self, command_line_arguments):
        application_export_subdirectory = self.__get_export_folder_path(command_line_arguments)
        # TODO: Check if the directory already exists, and issue a warning if
        # so. I would like to introduce a command-line argument `--force` to
        # force writing to a directory that already exists.
        # Or we could also make it such that the subdirectory is named after the
        # title itself!
        # os.path.exists(application_export_subdirectory)
        for index, context in enumerate(self.contexts):
            self.logger.info(f'Exporting assets in {context.filepath}')
            context.export_assets(application_export_subdirectory, command_line_arguments)

    # This is in a separate function becuase even on fast computers it 
    # can take a very long time and often isn't necessary.
    def export_metadata(self, command_line_arguments):
        application_export_subdirectory = self.__get_export_folder_path(command_line_arguments)
        self.logger.info(f'Exporting metadata for {self.system.filename}')
        self.system.export_metadata(application_export_subdirectory)
        for context in self.contexts:
            self.logger.info(f'Exporting metadata for {context.filename}')
            context.export_metadata(application_export_subdirectory)
        if self.profile is not None:
            self.logger.info(f'Exporting metadata for {self.profile.filename}')
            self.profile.export_metadata(application_export_subdirectory)

    def __get_export_folder_path(self, command_line_arguments):
        if self.system.game_title is not None:
            game_title = self.system.game_title
        else:
            # Early games like Lion King don't have game title metadata in the
            # BOOT.STM, so we must figure it out from context instead.
            # Currently, we just get a meaningful name from the folder where the
            # data files live. For example, if the input argument was
            #  ~/Media Station/Lion King - NA - 2.0GB - German - Windows/DATA,
            # we would name the export folder "Lion King - NA - 2.0GB - German - Windows".
            # TODO: Can we also try to get the name of the 
            # game executable if it's available?
            input_filepath = command_line_arguments.input[0]
            # Get the lowest directory in the path.
            if os.path.isfile(input_filepath):
                input_filepath = os.path.dirname(input_filepath)
            last_folder = os.path.basename(input_filepath)
            # The "data" folder isn't descriptive; we want to get the parent
            # folder if just the "data" folder was passed in.
            if last_folder.lower() == "data":
                game_title = os.path.basename(os.path.dirname(input_filepath))
            else:
                game_title = last_folder

        return os.path.join(
            command_line_arguments.export, 
            self.__make_name_filepath_safe(self.application_name), 
            self.__make_name_filepath_safe(game_title))

    ## A small helper function to remove any odd characters from a name.
    def __make_name_filepath_safe(self, name: str) -> str:
        return "".join([c if c.isalnum() or c in (' ', '.', '_') else '_' for c in name])

class MediaStationCommandLineArguments(CommandLineArguments):
    def __init__(self, application_name: str, application_description: str):
        # ADD COMMAND-LINE ARGUMENTS FOR SKIPPING METADATA EXPORT.
        super().__init__(application_name, application_description)
        metadata_export_help = "Skip metadata (JSON) export; only write assets. This option is provided because metadata export is currently SLOW."
        self.argument_parser.add_argument('--skip-metadata-export', action = "store_true", default = False, help = metadata_export_help)

def main(raw_command_line: List[str] = None):
    # PARSE THE COMMAND-LINE ARGUMENTS.
    APPLICATION_NAME = 'Media Station'
    APPLICATION_DESCRIPTION = ''
    command_line = MediaStationCommandLineArguments(APPLICATION_NAME, APPLICATION_DESCRIPTION)
    command_line_arguments = command_line.parse(raw_command_line)

    # PARSE THE ASSETS.
    media_station_engine = MediaStationEngine(APPLICATION_NAME)
    if command_line_arguments.debug:
        media_station_engine.logger.setLevel(logging.DEBUG)
    global_variables.application = media_station_engine
    media_station_engine.process(command_line_arguments.input)

    # EXPORT THE ASSETS, IF REQUESTED.
    if command_line_arguments.export:
        media_station_engine.export_assets(command_line_arguments)
        if not command_line_arguments.skip_metadata_export:
            media_station_engine.export_metadata(command_line_arguments)

# TODO: Get good documentation here.
if __name__ == '__main__':
    main()

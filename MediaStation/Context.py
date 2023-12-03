
from enum import IntEnum
from typing import Dict, List, Optional

from asset_extraction_framework.Asserts import assert_equal
from asset_extraction_framework.File import File
from asset_extraction_framework.Asset.Palette import RgbPalette

from . import global_variables
from .Assets.Bitmap import Bitmap
from .Assets.BitmapSet import BitmapSet
from .Assets.Asset import Asset
from .Assets.Script import Script
from .Primitives.Datum import Datum
from .Riff.DataFile import DataFile

class ChunkType(IntEnum):
    HEADER = 0x000d
    IMAGE = 0x0018

## Contains parameters for the entire context, including the following:
## - File number,
## - Human-readable name,
## - Any bytecode that runs when the context is first loaded (maybe).
##
## This is usually the second header section in a context, after the palette (if present).
class GlobalParameters:
    class SectionType(IntEnum):
        EMPTY = 0x0014
        NAME = 0x0bb9
        FILE_NUMBER_SECTION = 0x0011

    ## Reads context parametersfrom the binary stream at its current position.
    ## The number of bytes read from the stream depends on the type 
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, stream):
        # Titles that use the old-style format don't have human-readable context names.
        # When the names are present, they generally look like the following: "Decals_7x00".
        self.name: Optional[str] = None
        # TODO: Understand what this declaration is.
        self.entries = {}
        # This is not an internal file ID, but the number of the file
        # as it appears in the filename. For instance, the context in
        # "100.cxt" would have file number 100.
        self.file_number: int = Datum(stream).d

        # READ THE SECTIONS.
        section_type: int = Datum(stream).d
        if section_type != GlobalParameters.SectionType.EMPTY:
            if section_type == GlobalParameters.SectionType.NAME:
                assert_equal(Datum(stream).d, self.file_number)
                self.name = Datum(stream).d
                assert_equal(Datum(stream).d, 0x0000)

            elif section_type == GlobalParameters.SectionType.FILE_NUMBER_SECTION:
                self.read_file_number_section(stream)
        else:
            # TODO: Document what this stuff is. My original code had zero documentation.
            type = Datum(stream)
            while type.d != 0x0000:
                assert_equal(type.d, self.file_number, "file ID")
                entries = []

                id = Datum(stream)
                self.entries.update({id.d: self.entity(Datum(stream), stream)})

                check = Datum(stream)
                if check.d != 0x0014:
                    break

                type = Datum(stream)

            if check.d == 0x0011: 
                self.read_file_number_section(stream)

        # READ THE CONTEXT-GLOBAL BYTECODE.
        # TODO: Does this run when the context is first loaded?
        if global_variables.version.is_first_generation_engine:
            token = Datum(stream)
            self.init = []
            while token.d == 0x0017:
                self.init.append(Script(stream, in_independent_asset_chunk = False))
                token = Datum(stream)

    # TODO: Document what this stuff is. My original code had zero documentation.
    def entity(self, token, stream):
        entries = []

        if token.d == 0x0007: # array
            size = Datum(stream)
            for _ in range(size.d):
                entries.append(self.entity(Datum(stream), stream))
        elif token.d == 0x0006: # string
            size = Datum(stream)
            entries.append(stream.read(size.d).decode("utf-8"))
        else: 
            entries.append(Datum(stream).d)

        return {"token": token.d, "entries": entries}

    ## I don't know what this structure is, but it's in every old-style game.
    ## The fields aside from the file numbers are constant.
    ## \param[in] stream - A binary stream that supports the read method.
    def read_file_number_section(self, stream):
        # VERIFY THE FILE NUMBER.
        repeated_file_number = Datum(stream).d
        assert_equal(repeated_file_number, self.file_number)

        # READ THE UNKNOWN FIELD.
        unk = Datum(stream).d
        assert_equal(unk, 0x0001)

        # VERIFY THE FILE NUMBER.
        repeated_file_number = Datum(stream).d
        assert_equal(repeated_file_number, self.file_number)

        # READ THE UNKNOWN FIELD.
        unk = Datum(stream).d
        assert_equal(unk, 0x0022)

        # TODO: Understand what this is.
        Datum(stream)

## A "context" is the logical entity serialized in each CXT data file.
## Subfile 0 of this file always contains the header sections for the context.
##  - Subfile 0: 
##    - A series of header sections that stores things like palettes, asset metadata (coordinates, dimensions, etc.),
##      and bytecode. Generally, most data except for actual sound/image data is stored here.
##    - In the old-style format, header sections are stored in a single igod chunk.
##      In the new-style format, header sections are stored in their own igod chunks.
##    - After all the header chunks, a000-style chunks that generally store movie still bitmaps or short sounds.
##      These are "chunk-only" assets.
##      (Movies and longer sounds are generally placed in their own subfiles below, but there are exceptions to this.)
##
##  - Subfile 1: The sound/image data for one sound/movie asset.
##    These are "subfiled" assets because they are stored in subfiles.
##    ...
##  - Subfile n: The sound/image data for one sound/movie asset.
class Context(DataFile):
    ## Defines the sections that can occur in CXT files.
    ## All of these sections occur only as header sections.
    class SectionType(IntEnum):
        EMPTY = 0x0000
        OLD_STYLE = 0x000d
        CONTEXT_PARAMETERS = 0x000e
        PALETTE = 0x05aa
        END = 0x0010
        ASSET_HEADER = 0x0011
        POOH = 0x057a
        ASSET_LINK = 0x0013
        FUNCTION = 0x0031

    ## Parses a context from the given location.
    ## \param[in] - filepath: The filepath of the file, if it exists on the filesystem.
    ##                        Defaults to None if not provided.
    ## \param[in] - stream: A BytesIO-like object that holds the file data, if the file does
    ##                      not exist on the filesystem.
    ## NOTE: It is an error to provide both a filepath and a stream, as the source of the data
    ##       is then ambiguous.
    def __init__(self, filepath: str = None, stream = None):
        super().__init__(filepath = filepath, stream = stream, has_header = True)
        self.assets: Dict[str, Asset] = {}
        self._referenced_chunks: Dict[str, Asset] = {}
        self.links = []
        # Since this is a separate header section, it is parsed by its own class
        # rather than being read through a method in this class. That adds some 
        # indirection, but it helps preserve conceptual integrity of the design.
        self.parameters: Optional[GlobalParameters] = None
        # All images in this context use this same palette, if one is provided.
        # There is no facility for palette changes within a context.
        # This makes handling images a lot simpler!
        self.palette = None

        # VERIFY THE FILE IS NOT EMPTY.
        # A few Lion King contexts do not actually have any real; all they have
        # is a 16-byte header. There is no data to process for these, so
        # exit now if we find one of these.
        if self.header_only:
            return

        # READ THE HEADER SECTIONS.
        # TODO: Implement a better version checking system here.
        subfile = self.get_next_subfile()
        chunk = subfile.get_next_chunk()
        if global_variables.version.is_first_generation_engine:
            self.read_old_style_header_sections(subfile, chunk)
            # TODO: Understand why, with the new chunk reading, an extra datum
            # previously needed to be read here but no longer needs to be read.
            chunk = subfile.get_next_chunk()
        else:
            chunk = self.read_new_style_header_sections(subfile, chunk)
        if self.palette is None:
            print('WARNING: No palette provided for this context.')

        # READ THE CHUNK-ONLY ASSETS.
        # These are assets stored in the first subfile only.
        while not subfile.at_end:
            self.read_asset_in_first_subfile(chunk)
            if not subfile.at_end:
                chunk = subfile.get_next_chunk()

        # READ THE ASSETS IN THE REST OF THE SUBFILES.
        # These are the "subfiled" assets, because their data is each stored in 
        # its own subfile.
        # TODO: Should this be lazy, so we only read the rest of the subfiles
        # on demand? That is probably what the original did, and that's why 
        # you needed each of the subfiles to be listed in the BOOT.STM.
        for index in range(self.subfile_count - 1):
            # UPDATE THE CURRENT SUBFILE.
            subfile = self.get_next_subfile()
            self.read_asset_from_later_subfile(subfile)

    ## Reads old-style header chunks from the current position of this file's binary stream.
    ##
    ## In the old-style file format, all header chunks EXCEPT the palette are lumped into one igod
    ## chunk; they do not have separate chunks. This caused some craziness and I'm glad Media
    ## Station put the header chunks in separate igod chunks in later versions. Thankfully the
    ## header chunk types are the same in both the old-style and new-style.
    ##
    ## The following titles use the old-style file format and thus must use this structure:
    ##  - Lion King (the OG of the OG, haha)
    ##  - Pocahontas
    ## TODO: Finish off this list.
    def read_old_style_header_sections(self, subfile, chunk):
        # VERIFY THIS DATA CHUNK IS A LEGACY HEADER.
        section_type = Datum(chunk).d
        assert_equal(section_type, Context.SectionType.OLD_STYLE)

        # READ THE PALETTE.
        # In the old-style format, the palette is ALWAYS the only header section
        # in the first igod chunk.
        #
        # The parser does not enforce this, so technically the header section read
        # for this first chunk could be something else, but I haven't ever observed that.
        self.read_header_section(chunk)

        # GET THE NEXT DATA CHUNK.
        # The rest of the header sections after the palette are in the next igod chunk.
        chunk = subfile.get_next_chunk()

        # READ ALL THE HEADER SECTIONS.
        section_type = Datum(chunk).d
        assert_equal(section_type, Context.SectionType.OLD_STYLE)
        more_sections_to_read: bool = True
        while more_sections_to_read:
            # READ THIS SECTION.
            more_sections_to_read = self.read_header_section(chunk)
            if not more_sections_to_read:
                # Some conditions force an immediate end to reading sections,
                # even before the data in the chunk runs out.
                # TODO: Document these better.
                break

            # CHECK IF THERE ARE MORE SECTIONS TO READ.
            more_sections_to_read = (not chunk.at_end)

    ## Reads new-style header chunks from the current position of this file's binary stream.
    ##
    ## In the new-style file format, each header section has a separate igod chunk.
    ## This makes parsing much easier than with the old-style format.
    def read_new_style_header_sections(self, subfile, chunk):
        # READ ALL THE HEADER SECTIONS.
        more_sections_to_read = chunk.is_igod
        while more_sections_to_read:
            # VERIFY THIS IGOD CHUNK IS A HEADER.
            chunk_is_header = (Datum(chunk).d == ChunkType.HEADER)
            if not chunk_is_header:
                break

            # READ THIS DATA CHUNK.
            more_chunks_to_read: bool = self.read_header_section(chunk)
            if not more_chunks_to_read:
                break

            # QUEUE UP THE NEXT DATA CHUNK.
            if subfile.at_end:
                more_sections_to_read = False
            else:
                chunk = subfile.get_next_chunk()
                more_sections_to_read = chunk.is_igod
        return chunk

    ## Reads a header section from this file's binary stream from the current position.
    ## \return True if there are more chunks to read after this one; False otherwise.
    ##         Note that there are times other than when this function returns False.
    def read_header_section(self, chunk, reading_stage = False):
        section_type = Datum(chunk).d
        if (Context.SectionType.CONTEXT_PARAMETERS == section_type):
            # VERIFY THIS CONTEXT DOES NOT ALREADY HAVE PARAMETERS.
            if self.parameters is not None:
                raise ValueError('More than one parameters structure present in context.')
            self.parameters = GlobalParameters(chunk)

        elif (Context.SectionType.ASSET_LINK == section_type):
            # TODO: Figure out what is going on here.
            asset_link = Datum(chunk).d
            self.links.append(asset_link)
            self.read_header_section(chunk, reading_stage = reading_stage)

        elif (Context.SectionType.PALETTE == section_type):
            # VERIFY THIS CONTEXT DOES NOT ALREADY HAVE A PALETTE.
            # We can only have one palette for each context.
            if self.palette is not None:
                raise ValueError('More than one palette present in context.')
            self.palette = RgbPalette(self.stream, has_entry_alignment = False)
            Datum(chunk).d

        elif (Context.SectionType.ASSET_HEADER == section_type):
            # READ AN ASSET HEADER.
            asset_header = Asset(chunk)
            self.assets.update({asset_header.id: asset_header})
            if (Asset.AssetType.STAGE == asset_header.type):
                # TODO: Figure out what these are. Are they always zero?
                Datum(chunk)
                Datum(chunk)

                # TODO: Correctly handle embedded stages.
                if reading_stage:
                    print('WARNING: Found embedded stage, there mght be trouble afoot.')

                # READ THE ASSET HEADERS IN THE STAGE.
                another_asset_header = self.read_header_section(chunk, reading_stage = True)
                while another_asset_header:
                    another_asset_header = self.read_header_section(chunk, reading_stage = True)

            # REGISTER ANY REFERENCED CHUNKS.
            if len(asset_header.chunk_references) > 0:
                # For movies, the first chunk is sufficient to identify
                # the movie since the IDs of the three chunks are always 
                # sequential.
                for chunk_reference in asset_header.chunk_references:
                    self._referenced_chunks.update({chunk_reference: asset_header})

            if (not chunk.at_end) and \
                (not global_variables.version.is_first_generation_engine) and \
                (not reading_stage) and \
                (not asset_header.type == Asset.AssetType.STAGE):
                Datum(chunk).d

            # TODO: I think this is related to embedded stages.
            if (chunk.at_end) and reading_stage:
                return False

        elif (Context.SectionType.FUNCTION == section_type):
            function = Script(chunk, in_independent_asset_chunk = True)
            self.assets.update({function.id: function})

        elif (Context.SectionType.END == section_type):
            # TODO: Figure out what these are.
            Datum(chunk)
            Datum(chunk)
            return False

        elif (Context.SectionType.EMPTY == section_type):
            # THIS IS AN EMPTY SECTION.
            if reading_stage:
                return False
            else:
                pass

        elif (Context.SectionType.POOH == section_type):
            # TODO: Understand what this is.
            list(map(lambda x: assert_equal(Datum(chunk).d, x),
                [0x04, 0x04, 0x012c, 0x03, 0.50, 0x01, 1.00, 0x01, 254.00, 0x00]
            ))

        else:
            raise ValueError(f'Unknown section type: {section_type:04x}')

        return True

    ## Reads an asset in the first subfile of this context, from the binary stream
    ## at its current position. The asset header for this asset must have already 
    ## been read. 
    def read_asset_in_first_subfile(self, chunk):
        # MAKE SURE THIS IS NOT AN ASSET LINK.
        # TODO: Properly understand what these data structures are.
        if chunk.is_igod:
            chunk.read(chunk.length)
            return

        # RETRIEVE THE ASSET HEADER.
        header = self.get_asset_by_chunk_id(chunk.fourcc)
        if header is None:
            # Look in the whole application before throwing an error, as this could be the 
            # INSTALL.CXT case.
            header = global_variables.application.get_asset_by_chunk_id(chunk.fourcc)
            if header is None:
                # This should never actually be an error condition in valid contexts, because the asset headers are also in the first subfile.
                raise ValueError(
                    f'Asset FourCC {chunk.fourcc} was encountered in the first subfile, but no asset header read thus far has declared this FourCC.\n\n'
                    'This is expected if you are trying to extract assets from an INSTALL.CXT without any other contexts, as INSTALL.CXT does not contain any asset headers.\n'
                    'Try running the extraction again on the entire game directory.')

        # READ THE ASSET ACCORDING TO ITS TYPE.
        if (header.type == Asset.AssetType.IMAGE):
            header.image = Bitmap(chunk)

        elif (header.type == Asset.AssetType.CAMERA):
            header.image = Bitmap(chunk)

        elif (header.type == Asset.AssetType.IMAGE_SET):
            header.image_set.read_chunk(chunk)

        elif (header.type == Asset.AssetType.SOUND):
            header.sound.read_chunk(chunk)

        elif (header.type == Asset.AssetType.SPRITE):
            header.sprite.append(chunk)

        elif (header.type == Asset.AssetType.FONT):
            header.font.append(chunk)

        elif (header.type == Asset.AssetType.MOVIE):
            # READ A MOVIE STILL IMAGE.
            # Animated movie frames are always stored in other subfiles. 
            # Any movie chunk that occurs in the first subfile is a "still"
            # that displays when the movie is not playing (because, for instance,
            # the user has not clicked the hotspot to make it play).
            header.movie.add_still(chunk)
    
        else:
            raise ValueError(f'Unknown asset type in first subfile: {header.type}')

    ## Reads an asset from a subfile after the first subfile.
    def read_asset_from_later_subfile(self, subfile):
        # RETRIEVE THE ASSET HEADER.
        chunk = subfile.get_next_chunk()
        header = self.get_asset_by_chunk_id(chunk.fourcc)
        if header is None:
            # Look in the whole application before throwing an error, as this could be the 
            # INSTALL.CXT case.
            header = global_variables.application.get_asset_by_chunk_id(chunk.fourcc)
            if header is None:
                raise ValueError(
                    f'Asset FourCC {chunk.fourcc} was encountered in a subfile, but no asset header read thus far has declared this FourCC.\n\n'
                    'This is expected if you are trying to extract assets from an INSTALL.CXT without any other contexts, as INSTALL.CXT does not contain any asset headers.\n'
                    'Try running the extraction again on the entire game directory.')

        # READ THE ASSET ACCORDING TO ITS TYPE.
        if header.type == Asset.AssetType.MOVIE:
            header.movie.add_subfile(subfile, chunk)

        elif header.type == Asset.AssetType.SOUND:
            header.sound.read_subfile(subfile, chunk, header.total_chunks)

        elif header.type == Asset.AssetType.IMAGE_SET:
            header.image_set.read_subfile(subfile, chunk)

        else:
            raise ValueError(f'Unknown subfile asset type: {header.type}')

    ## This is included as a separate step becuase it is not connected to reading the data.
    def apply_palette(self):
        for asset in self._referenced_chunks.values():
            if (asset.type == Asset.AssetType.IMAGE) or \
                    (asset.type == Asset.AssetType.CAMERA):
                asset.image._palette = self.palette

            elif (asset.type == Asset.AssetType.IMAGE_SET):
                asset.image_set.apply_palette(self.palette)

            elif (asset.type == Asset.AssetType.SPRITE):
                for frame in asset.sprite.frames:
                    frame._palette = self.palette

            elif (asset.type == Asset.AssetType.FONT):
                for frame in asset.font.glyphs:
                    frame._palette = self.palette

            elif (asset.type == Asset.AssetType.MOVIE):
                for frame in asset.movie.frames:
                    frame._palette = self.palette

    ## \return The asset whose chunk ID matches the provided chunk ID.
    ##         (For movie assets, the chunk ID used for lookup is the first chunk.)
    ##         If an asset does not match, None is returned.
    def get_asset_by_chunk_id(self, chunk_id: str) -> Optional[Asset]:
        return self._referenced_chunks.get(chunk_id, None)

    ## Exports all the assets in this file.
    ## \param[in] root_directory_path - The root directory where the assets should be exported.
    ##            A subdirectory named after this file will be created in the root, 
    ##            and asset exporters may create initial subdirectories.
    ## \param[in] command_line_arguments - All the command-line arguments provided to the 
    ##            script that invoked this function, so asset exporters can read any 
    ##            necessary formatting options.
    ## \return The subdirectory named after this file created in the provided root.
    def export(self, root_directory_path: str, command_line_arguments) -> str:
        # APPLY THE PALETTE TO ALL IMAGES IN THIS CONTEXT.
        # This is done as a seperate step becuase it is not associated with reading the data
        # but is part of post-processing and preparing for export.
        # TODO: For contexts that have palettes, the palette of the context is generally the palette
        # of all the images in that context. However, some contexts do not have palettes. This occurs
        # in a few known cases:
        #  - 
        #  - INSTALL.CXT, which contains assets that are declared in other contexts.
        self.apply_palette()

        super().export(root_directory_path, command_line_arguments)
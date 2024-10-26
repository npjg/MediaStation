
from enum import IntEnum
from typing import List, Optional

from asset_extraction_framework.Asserts import assert_equal
from asset_extraction_framework.File import File
from asset_extraction_framework.Exceptions import BinaryParsingError
import self_documenting_struct as struct

from . import global_variables
from .Riff.DataFile import DataFile
from .Primitives.Datum import Datum
from .Primitives.Point import Point

## Contains information about the engine (also called
##  "title compiler") used in this particular game.
## Engine version information is not present in early games,
## so all the fields are initialized to be None.
class VersionInfo:
    def __init__(self, stream = None):
        self.major_version = None
        self.minor_version = None
        self.revision_number = None
        self.string = None
        if stream is not None:
            # The version number of this engine, in the form 4.0r8 (major . minor r revision).
            self.major_version = Datum(stream, Datum.Type.UINT16_1).d
            self.minor_version = Datum(stream, Datum.Type.UINT16_1).d
            self.revision_number = Datum(stream, Datum.Type.UINT16_1).d
            # A textual description of this engine.
            # Example: "Title Compiler T4.0r8 built Feb 13 1998 10:16:52"
            #           ^^^^^^^^^^^^^^  ^^^^^
            #           | Engine name   | Version number
            self.string = Datum(stream, Datum.Type.STRING).d

            # LOG THE TITLE INFORMATION FOR DEBUGGING PURPOSES.
            print(f' {self.string} - {self.version_number}')

    ## Engine version information is not present in version 1 games,
    ## so all the fields are initialized to be None.
    @property
    def is_first_generation_engine(self) -> bool:
        return (self.major_version is None) and \
            (self.minor_version is None) and \
            (self.revision_number is None) and \
            (self.string is None)

    @property
    def version_number(self) -> str:
        return f'{self.major_version}.{self.minor_version}r{self.revision_number}'

## A "context" is the logical entity serialized in each CXT file.
## (As I understand it, "scene" is more commonly used a synonym for "context".)
## CXT files do not have the same names as the contexts they contain.
## For example, a file named "109.CXT" might have a context called 
## "Root_7x00". The "109" is called the context's "file number".
## 
## This extra naming indirection is probably to allow contexts to have longer, more
## descriptive names while preserving compatibility with operating systems that used 
## 8.3 filenames.
##
##  - Maps context names to CXT filenames (indirectly).
##  - Includes files referenced by this file.
## TODO: Maybe these can be generalized into a Declaration parent class?
## To handle all the odd section type stuff. But then we get into metaprogramming...
class ContextDeclaration:
    ## Defines each of the sections in this data structure.
    ## Usually there is one section for each type of data stored
    ## plus a special "empty" section.
    class SectionType(IntEnum):
        EMPTY = 0x0000
        PLACEHOLDER = 0x0003
        FILE_NUMBER_1 = 0x0004
        FILE_NUMBER_2 = 0x0005
        FILE_REFERENCE = 0x0006
        CONTEXT_NAME = 0x0bb8

    def __init__(self, chunk):
        # ENSURE WE HAVEN'T REACHED THE END OF THE DECLARATIONS.
        section_type = Datum(chunk, Datum.Type.UINT16_1).d
        if (ContextDeclaration.SectionType.EMPTY == section_type):
            self._is_last = True
            return
        else:
            # TODO: Should there be assertion for exactly what this other
            # section type might need to be?
            #
            # There may be more declarations in the stream.
            self._is_last = False
        
        # DECLARE THE CONTEXT METADATA.
        # Denotes the other files reference within this file.
        # These references are stored as file numbers (see below
        # for a definition of file numbers).
        self.file_references = []
        # The file number of the file that contains this context.
        #
        # This is the number that is in the filename and NOT the internal ID
        # for the filename. For instance, context "Root_7x00" in file "109.cxt"
        # would have file number 109.
        self.file_number = None
        # This is the context's descriptive name, as opposed
        # to the filename that consists of the file number and a CXT extension.
        self.context_name = None

        # READ THE FILE REFERENCES.
        while ContextDeclaration.SectionType.FILE_REFERENCE == section_type:
            file_reference = Datum(chunk, Datum.Type.UINT16_1).d
            self.file_references.append(file_reference)
            section_type = Datum(chunk, Datum.Type.UINT16_1).d

        # READ THE OTHER CONTEXT METADATA.
        if ContextDeclaration.SectionType.PLACEHOLDER == section_type:
            # READ THE FILE NUMBER.
            section_type = Datum(chunk, Datum.Type.UINT16_1).d
            assert_equal(section_type, ContextDeclaration.SectionType.FILE_NUMBER_1)
            self.file_number = Datum(chunk, Datum.Type.UINT16_1).d
            # I don't know why the file number is always repeated. 
            # Is it just for data integrity, or is there some other reason?
            section_type = Datum(chunk, Datum.Type.UINT16_1).d
            assert_equal(section_type, ContextDeclaration.SectionType.FILE_NUMBER_2)
            repeated_file_number = Datum(chunk, Datum.Type.UINT16_1).d
            assert_equal(repeated_file_number, self.file_number)

            # READ THE CONTEXT NAME.
            # Only some titles have context names, and unfortunately we can't
            # determine which just by relying on the title compiler version
            # number.
            # TODO: Find a better way to read the context name without relying
            # on reading and rewinding.
            rewind_pointer = chunk.stream.tell()
            section_type = Datum(chunk, Datum.Type.UINT16_1).d
            if ContextDeclaration.SectionType.CONTEXT_NAME == section_type:
                # READ THE CONTEXT NAME.
                self.context_name = Datum(chunk, Datum.Type.STRING).d
            else:
                # THERE IS NO CONTEXT NAME.
                # We have instead read into the next declaration, so let's undo that.
                chunk.stream.seek(rewind_pointer)
                
        elif ContextDeclaration.SectionType.EMPTY == section_type:
            # INDICATE THIS IS THE LAST CONTEXT DECLARATION.
            # This signals to the holder of this declaration that there
            # are no more declarations in the stream.
            self._is_last = True

        else:
            # INDICATE AN ERROR.
            raise ValueError(f'Received unexpected section type: 0x{section_type:04x}')

## TODO: Understand what this is.
class UnknownDeclaration:
    ## Defines each of the sections in this data structure.
    ## Usually there is one section for each type of data stored
    ## plus a special "empty" section.
    class SectionType(IntEnum):
        EMPTY = 0x0000
        UNK_1 = 0x0009
        UNK_2 = 0x0004

    def __init__(self, stream):
        # ENSURE WE HAVEN'T REACHED THE END OF THE DECLARATIONS.
        section_type: int = Datum(stream, Datum.Type.UINT16_1).d
        if (UnknownDeclaration.SectionType.EMPTY == section_type):
            self._is_last: bool = True
            return
        else:
            # TODO: Should there be assertion for exactly what this other
            # section type might need to be?
            #
            # There are more declarations in the stream.
            self._is_last: bool = False

        # READ THE UNKNOWN FIELD.
        section_type = Datum(stream, Datum.Type.UINT16_1).d
        assert_equal(section_type, UnknownDeclaration.SectionType.UNK_1)
        self.unk: int = Datum(stream, Datum.Type.UINT16_1).d

        # VERIFY THE COPY OF THE UNKNOWN FIELD.
        # This is always the same as the previous one.
        section_type = Datum(stream, Datum.Type.UINT16_1).d
        assert_equal(section_type, UnknownDeclaration.SectionType.UNK_2)
        repeated_unk = Datum(stream, Datum.Type.UINT16_1).d
        assert_equal(repeated_unk, self.unk)

## Declares a data file in the game's data directory.
## Usually every file that has a CXT extension is declared here.
## This does not contain information on the context in the file,
## but information about the file itself (like its name and its
## intended installation location).
class FileDeclaration:
    ## Defines each of the sections in this data structure.
    ## Usually there is one section for each type of data stored
    ## plus a special "empty" section.
    class SectionType(IntEnum):
        EMPTY = 0x0000
        FILE_ID = 0x002b
        FILE_NAME_AND_TYPE = 0x002d

    ## Indicates where this file is intended to be read from.
    ## NOTE: This might not be correct and this might be a more general "file type".
    class IntendedFileLocation(IntEnum):
        # Usually all files that have numbers remain on the CD-ROM.
        CD_ROM = 0x0007
        # I wonder if one of these means it's loaded in memory at all times?
        UNK1 = 0x0008
        UNK2 = 0x0009
        # Usually only INSTALL.CXT is copied to the hard disk.
        HARD_DISK = 0x000b

    ## Reads a file declaration from a binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, stream):
        # ENSURE WE HAVEN'T REACHED THE END OF THE DECLARATIONS.
        section_type: int = Datum(stream, Datum.Type.UINT16_1).d
        if (FileDeclaration.SectionType.EMPTY == section_type):
            self._is_last = True
            return
        else:
            # TODO: Should there be assertion for exactly what this other
            # section type might need to be?
            #
            # There are more declarations in the stream.
            self._is_last = False

        # READ THE FILE ID.
        # This is NOT the same as the "file number" referenced in context
        # declarations. This is usually a strictly ascending ID that usually
        # starts from 100 and seems unrelated to other values used to identify files.
        # Again, I'm not sure the need for this added complexity.
        section_type = Datum(stream, Datum.Type.UINT16_1).d
        assert_equal(section_type, FileDeclaration.SectionType.FILE_ID)
        self.id = Datum(stream, Datum.Type.UINT16_1).d

        # READ THE INTENDED LOCATION OF THE FILE.
        section_type = Datum(stream, Datum.Type.UINT16_1).d
        assert_equal(section_type, FileDeclaration.SectionType.FILE_NAME_AND_TYPE)
        self.intended_location = FileDeclaration.IntendedFileLocation(Datum(stream, Datum.Type.UINT16_1).d)

        # READ THE CASE-INSENSITIVE FILENAME.
        # Since the platforms that Media Station originally targeted were case-insensitive,
        # the case of these filenames might not match the case of the files actually in 
        # the directory. All files should be matched case-insensitively.
        self.name: str = Datum(stream, Datum.Type.FILENAME).d

## Declares a RIFF subfile in a data file.
class SubfileDeclaration:
    ## Defines each of the sections in this data structure.
    ## Usually there is one section for each type of data stored
    ## plus a special "empty" section.
    class SectionType(IntEnum):
        EMPTY = 0x0000
        ASSET_ID = 0x002a
        FILE_ID = 0x002b
        START_OFFSET = 0x002c

    ## Reads a subfile declaration from a binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, stream):
        # ENSURE WE HAVEN'T REACHED THE END OF THE DECLARATIONS.
        section_type: int = Datum(stream, Datum.Type.UINT16_1).d
        if (ContextDeclaration.SectionType.EMPTY == section_type):
            self._is_last = True
            return
        else:
            # TODO: Should there be assertion for exactly what this other
            # section type might need to be? Seems like this is 0x28 when
            # we haven't reached the end of the declarations.
            #
            # There may be more declarations in the stream.
            self._is_last = False

        # READ THE ASSET ID.
        # If this subfile is the asset headers subfile, the asset ID
        # will be the same as the file number of the respective context.
        section_type = Datum(stream, Datum.Type.UINT16_1).d
        assert_equal(section_type, SubfileDeclaration.SectionType.ASSET_ID)
        self.asset_id: int = Datum(stream, Datum.Type.UINT16_1).d

        # READ THE FILE ID.
        # This is the file ID as defined in the file declarations and NOT
        # the "file number" provided in the context declarations.
        section_type = Datum(stream, Datum.Type.UINT16_1).d
        assert_equal(section_type, SubfileDeclaration.SectionType.FILE_ID)
        self.file_id: int = Datum(stream, Datum.Type.UINT16_1).d

        # READ THE START OFFSET IN THE GIVEN FILE.
        # This is from the absolute start of the given file.
        section_type = Datum(stream, Datum.Type.UINT16_1).d
        assert_equal(section_type, SubfileDeclaration.SectionType.START_OFFSET)
        self.start_offset_in_file: int = Datum(stream, Datum.Type.UINT32_1).d

## Declares a cursor, which is stored as a cursor resource in the game executable.
class CursorDeclaration:
    ## Reads a cursor declaration from a binary stream at its current position.
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, stream):
        # READ THE CURSOR RESOURCE.
        unk1 = Datum(stream, Datum.Type.UINT16_1).d # Always 0x0001
        self.id: int = Datum(stream, Datum.Type.UINT16_1).d
        self.unk: int = Datum(stream, Datum.Type.UINT16_1).d
        self.name: str = Datum(stream, Datum.Type.FILENAME).d

## Contains metadata about the game and its native data files,
## usually all files with a CXT extension. (Additional files 
## like 3D models are not detailed in the .)
##
## Generally corresponds to the file "BOOT.STM". The "System" name
## comes as the most likely meaning of the "STM" extension.
##
## The data is generally, but not always, presented in the following order:
##  - Game title
##  - Engine version
##  - 
class System(DataFile):
    class SectionType(IntEnum):
        LAST = 0x0000
        # This semems to separate the cursor declarations from whatever comes
        # after it (what I formerly called the "footer"), but it has no data
        # itself.
        EMPTY = 0x002e 
        ENTRY_SCREEN = 0x002f
        CONTEXT_DECLARATION = 0x0002
        VERSION_INFORMATION = 0x0190
        UNK1 = 0x0191
        UNK2 = 0x0192
        UNK3 = 0x0193
        ENGINE_RESOURCE_NAME = 0x0bba
        ENGINE_RESOURCE_ID = 0x0bbb
        UNKNOWN_DECLARATION = 0x0007
        FILE_DECLARATION = 0x000a
        SUBFILE_DECLARATION = 0x000b
        UNK5 = 0x000c
        CURSOR_DECLARATION = 0x0015
        ALLOW_MULTIPLE_SOUNDS = 0x0035
        ALLOW_MULTIPLE_STREAMS = 0x0036
        UNK4 = 0x057b

    ## Reads a system specification from the given location.
    ## \param[in] - filepath: The filepath of the file, if it exists on the filesystem.
    ##                        Defaults to None if not provided.
    ## \param[in] - stream: A BytesIO-like object that holds the file data, if the file does
    ##                      not exist on the filesystem.
    ## NOTE: It is an error to provide both a filepath and a stream, as the source of the data
    ##       is then ambiguous.
    def __init__(self, filepath: str = None, stream = None):
        # OPEN THE FILE FOR READING.
        # Systems do not have a Media Station header, probably
        # because the only ever have one subfile.
        super().__init__(filepath = filepath, stream = stream, has_header = False)
        # TODO: This should be integrated into the file itself.
        subfile = self.get_next_subfile()
        chunk = subfile.get_next_chunk()

        # DECLARE METADATA FOR THE WHOLE GAME.
        # These fields will not be present in early games.
        #
        # The name of this title. Usually slightly abbreviated,
        # like "tonka_gr" for Tonka Garage.
        self.game_title: str = None
        # This will not be present in early titles, using what I call 
        # "version 1" of the engine (Lion King era).
        self.version = VersionInfo()
        # A single string that contains several different pieces
        # of data about the source of this game.
        # Example: "Title Source ..\imt_src\TonkaGarage.imt; built Thu Mar 19 14:57:41 1998"
        #                        ^^^^^^^^^^^^^^^^^^^^^^^^^^        
        #                        | The IMT filepath; this was probably a metafile that defined each title.
        #                          Not useful unless we have the original source file (and PLEASE write if you do!)
        self.source_string: Optional[str] = None
        self.unknown_declarations = []
        self.file_declarations = []
        self.context_declarations = []
        self.riff_declarations = []
        self.cursor_declarations = []
        self.unks = []
        # These are not "resources" in the executable (like cursors) 
        # but are defined by the engine. Usually these names begin
        # with a dollar sign ($).
        self.engine_resource_names = []
        self.engine_resource_ids = []

        # READ THE ITEMS IN THIS FILE.
        # TODO: Figure out what this is.
        unk = Datum(chunk, Datum.Type.UINT16_1).d # Usually 0x0001
        global_variables.application.logger.debug(f'[System] unk = 0x{unk:0x}')
        section_type = Datum(chunk, Datum.Type.UINT16_1).d
        not_last_section = (System.SectionType.LAST != section_type)
        global_variables.version = VersionInfo()
        while not_last_section:
            global_variables.application.logger.debug(f'[System] Got section type: 0x{section_type:0x}')
            if section_type == System.SectionType.VERSION_INFORMATION: 
                self.game_title = Datum(chunk, Datum.Type.STRING).d
                print('---')
                print(f' {self.game_title}')
                # Interestingly, this next one is not wrapped in a datum!
                # TODO: Figure out what this is.
                unk = struct.unpack.uint16_le(chunk)
                global_variables.application.logger.debug(f'[System] unk = 0x{unk:0x}')
                self.version = VersionInfo(chunk)
                global_variables.version = self.version
                print(f' {self.version.string}')
                self.source_string = Datum(chunk, Datum.Type.STRING).d
                print(f' {self.source_string}')

            elif (System.SectionType.UNK1 == section_type) or \
                    (System.SectionType.UNK2 == section_type) or \
                    (System.SectionType.UNK3 == section_type):
                unk = Datum(chunk, Datum.Type.UINT16_1).d
                self.unks.append({hex(section_type): unk})
                global_variables.application.logger.debug(f"[System] unk = (section_type: 0x{section_type:0x}) 0x{unk:0x}")

            elif (System.SectionType.UNK4 == section_type):
                unk = Datum(chunk, Datum.Type.FLOAT64_1).d
                self.unks.append({hex(section_type): unk})
                global_variables.application.logger.debug(f"[System] unk = (section_type: 0x{section_type:0x}) {unk}")

            elif section_type == System.SectionType.ENGINE_RESOURCE_NAME:
                # READ THE NAME OF AN ENGINE RESOURCE.
                resource_name = Datum(chunk, Datum.Type.STRING).d
                self.engine_resource_names.append(resource_name)

            elif section_type == System.SectionType.ENGINE_RESOURCE_ID:
                # READ THE ID OF AN ENGINE RESOURCE.
                # This should correspond to the most previously read engine resource name.
                resource_id = Datum(chunk, Datum.Type.STRING).d
                self.engine_resource_ids.append(resource_id)

            elif section_type == System.SectionType.CONTEXT_DECLARATION:
                # READ THE CONTEXT DECLARATIONS.
                context_declaration = ContextDeclaration(chunk)
                while not context_declaration._is_last:
                    self.context_declarations.append(context_declaration)
                    context_declaration = ContextDeclaration(chunk)

            elif section_type == System.SectionType.UNKNOWN_DECLARATION:
                # READ THE UNKNOWN DECLARATIONS.
                file_declaration = UnknownDeclaration(chunk)
                while not file_declaration._is_last:
                    self.unknown_declarations.append(file_declaration)
                    file_declaration = UnknownDeclaration(chunk)

            elif section_type == System.SectionType.FILE_DECLARATION:
                # READ THE FILE DECLARATIONS.
                file_declaration = FileDeclaration(chunk)
                while not file_declaration._is_last:
                    self.file_declarations.append(file_declaration)
                    file_declaration = FileDeclaration(chunk)

            elif section_type == System.SectionType.SUBFILE_DECLARATION:
                # READ THE RIFF DECLARATIONS.
                riff_declaration = SubfileDeclaration(chunk)
                while not riff_declaration._is_last:
                    self.riff_declarations.append(riff_declaration)
                    riff_declaration = SubfileDeclaration(chunk)

            elif section_type == System.SectionType.CURSOR_DECLARATION:
                # READ THE CURSOR DECLARATIONS.
                cursor_declaration = CursorDeclaration(chunk)
                self.cursor_declarations.append(cursor_declaration)

            elif section_type == System.SectionType.EMPTY:
                pass

            elif section_type == System.SectionType.ENTRY_SCREEN:
                self.entry_context_id = Datum(chunk).d

            elif section_type == System.SectionType.ALLOW_MULTIPLE_SOUNDS:
                self.allow_multiple_sounds = bool(Datum(chunk).d)

            elif section_type == System.SectionType.ALLOW_MULTIPLE_STREAMS:
                self.allow_multiple_streams = bool(Datum(chunk).d)

            elif section_type == System.SectionType.UNK5:
                unk1 = Datum(chunk).d
                unk2 = Datum(chunk).d
                self.unks.append({hex(section_type): [unk1, unk2]})
                global_variables.application.logger.warning(f'[System] unk = (section_type: 0x{section_type:0x}) [{unk1} {unk2}]')

            else:
                # SIGNAL AN UNKNOWN SECTION.
                global_variables.application.logger.warning(f'[System] Detected unknown section 0x{section_type:04x}')

            # READ THE NEXT SECTION TYPE.
            section_type = Datum(chunk, Datum.Type.UINT16_1).d
            not_last_section = (System.SectionType.LAST != section_type)
        
        print('---')

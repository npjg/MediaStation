
from dataclasses import dataclass
from enum import IntEnum
import os

from asset_extraction_framework.Asserts import assert_equal
from asset_extraction_framework.Exceptions import BinaryParsingError

from ..Primitives.Datum import Datum
from ..Primitives.Polygon import Polygon
from .BitmapSet import BitmapSet, BitmapSetBitmapDeclaration
from .Font import Font
from .Movie import Movie
from .Script import Script
from .Sound import Sound
from .Sprite import Sprite
from . import Text

## A single asset, which is composed of teh following:
##  - A header section.
##  - For selected asset types, a member that holds a class.
##
## NOTE: Different asset types have different fields available. To avoid attribute errors,
## check the type member of an asset header before attempting to access a member.
class Asset:
    ## All of the known Media Station asset types. Always appear in header sections.
    ##
    ## The shorter strings in comments are known abbreviations
    ## for these types used in executable or data file strings.
    class AssetType(IntEnum):
        SCREEN  = 0x0001 # SCR
        STAGE  = 0x0002 # STG
        PATH  = 0x0004 # PTH
        SOUND  = 0x0005 # SND
        TIMER  = 0x0006 # TMR
        IMAGE  = 0x0007 # IMG
        HOTSPOT  = 0x000b # HSP
        SPRITE  = 0x000e # SPR
        LK_ZAZU = 0x000f
        LK_CONSTELLATIONS = 0x0010
        IMAGE_SET = 0x001d
        CURSOR  = 0x000c # CSR
        PRINTER  = 0x0019 # PRT
        MOVIE  = 0x0016 # MOV
        PALETTE  = 0x0017
        TEXT  = 0x001a # TXT
        FONT  = 0x001b # FON
        CAMERA  = 0x001c # CAM
        CANVAS  = 0x001e # CVS
        # TODO: Discover how the XSND differs from regular sounds.
        # Only appears in Ariel.
        XSND = 0x001f
        XSND_MIDI = 0x0020
        # TODO: Figure out what this is. Only appears in Ariel.
        RECORDER = 0x0021
        FUNCTION  = 0x0069 # FUN

    class SectionType(IntEnum):
        EMPTY = 0x0000
        BYTECODE_TRIGGER = 0x0017
        STAGE = 0x0019
        ASSET_ID = 0x001a
        CHUNK_REFERENCE = 0x001b
        ASSET_REFERENCE = 0x077b
        BOUNDING_BOX = 0x001c
        POLYGON = 0x001d
        Z_INDEX = 0x001e

    def export(self, directory_path, command_line_arguments):
        asset_references_data_from_other_asset = hasattr(self, 'asset_reference')
        if asset_references_data_from_other_asset:
            # TODO: Copy the referenced asset's data to this asset rather than just skipping export.
            return

        # These are the only asset types known to be "exportable"
        # (to have data that can't be represented well in JSON like images or sound).
        # If any more are discovered, they should be added here.
        if (Asset.AssetType.IMAGE == self.type):
            self.image.name = self.name
            self.image.export(directory_path, command_line_arguments)
        elif (Asset.AssetType.SOUND == self.type) or (Asset.AssetType.XSND == self.type):
            self.sound.name = self.name
            self.sound.export(directory_path, command_line_arguments)
        elif (Asset.AssetType.SPRITE == self.type):
            self.sprite.name = self.name
            self.sprite.export(directory_path, command_line_arguments)
        elif (Asset.AssetType.FONT == self.type):
            self.font.name = self.name
            self.font.export(directory_path, command_line_arguments)
        elif (Asset.AssetType.MOVIE == self.type):
            self.movie.name = self.name
            self.movie.export(directory_path, command_line_arguments)
        elif (Asset.AssetType.IMAGE_SET == self.type):
            self.image_set.name = self.name
            self.image_set.export(directory_path, command_line_arguments)
        elif (Asset.AssetType.STAGE == self.type):
            pass

    ## Reads an asset's header section from a binary stream at its current position.
    ## This initializes all metadata for the asset. For all assets EXCEPT the following,
    ## all asset data is included in the header section. But for these types, additional
    ## chunks or subfiles must be read:
    ##  - IMAGE
    ##  - CAMERA
    ##  - SOUND
    ##  - SPRITE
    ##  - FONT
    ##  - MOVIE
    ##  - UNK2
    ## \param[in] stream - A binary stream that supports the read method.
    def __init__(self, chunk):
        # READ THE UNIVERSAL MEMBERS FOR THIS ASSET.
        # These members are always present in all asset headers.
        #
        # The file number of the context that contains this asset.
        # For instance, an asset in file "100.CXT" would have file number 100.
        self.file_number: int = Datum(chunk).d
        self.name = None
        self.unks = []

        # READ THE ASSET TYPE.
        self.type = Asset.AssetType(Datum(chunk).d)
        if (Asset.AssetType.STAGE == self.type):
            self.children = None

        # The ID of this asset. Unique within each game.
        self.id: int = Datum(chunk).d

        # The asset ID of the stage on which this asset is shown.
        # None if the asset does not belong to a stage.
        self.stage_id = None
        self.chunk_references = []
        self.functions = []

        # READ THE SECTIONS IN THIS ASSET HEADER.
        # Due to the wide variation in fields that might be included, especially
        # when we are considering games that run different versions of the engine,
        # it was simplest to read each of the sections in a loop and populate
        # whatever the asset header contains.
        section_type: int = Datum(chunk).d
        more_sections_to_read = (Asset.SectionType.EMPTY != section_type)
        while more_sections_to_read:
            # READ THE CURRENT SECTION.
            self._read_section(section_type, chunk)

            # READ THE NEXT SECTION TYPE.
            section_type = Datum(chunk).d
            more_sections_to_read = (Asset.SectionType.EMPTY != section_type)

        # CREATE THE CHILDREN.
        if (Asset.AssetType.IMAGE == self.type):
            self.image = None
        elif (Asset.AssetType.IMAGE_SET == self.type):
            self.image_set = BitmapSet(self)
        elif (Asset.AssetType.CAMERA == self.type):
            self.camera = None
        elif (Asset.AssetType.SOUND == self.type) or (Asset.AssetType.XSND == self.type):
            self.sound = Sound(self.audio_encoding)
        elif (Asset.AssetType.SPRITE == self.type):
            self.sprite = Sprite(self)
        elif (Asset.AssetType.FONT == self.type):
            self.font = Font(self)
        elif (Asset.AssetType.MOVIE == self.type):
            self.movie = Movie(self)

    ## Reads all the various sections that can occur in an asset header.
    def _read_section(self, section_type, chunk):
        if Asset.SectionType.BYTECODE_TRIGGER == section_type: # TMR, MOV
            # READ A BYTECODE TRIGGER.
            # TODO: Define what this is.
            script = Script(chunk, in_independent_asset_chunk = False)
            self.functions.append(script)

        elif Asset.SectionType.STAGE == section_type: # All
            # READ A STAGE ASSET ID.
            self.stage_id = Datum(chunk).d

        elif Asset.SectionType.ASSET_ID == section_type:
            # READ THE ASSET ID.
            # We already have this asset's ID, so we will just verify it is the same
            # as the ID we have already read.
            duplicate_asset_id = Datum(chunk).d
            assert_equal(duplicate_asset_id, self.id, 'asset ID')

        elif Asset.SectionType.CHUNK_REFERENCE == section_type: # SND, IMG, SPR, MOV, FON
            # READ THE CHUNK REFERENCES.
            # These are references to the chunk(s) that hold the data for this asset.
            # The references and the chunks have the following format "a501".
            # There is no guarantee where these chunk(s) might actually be located:
            # - They might be in the same RIFF subfile as this header,
            # - They might be in a different RIFF subfile in the same CXT file,
            # - They might be in a different CXT file entirely.
            if self.type == Asset.AssetType.MOVIE:
                # READ THE HEADER REFERENCE.
                header_reference = Datum(chunk).d.chunk_id
                self.chunk_references.append(header_reference)
                # TODO: Find out what this is and why we have to skip it.
                self.unks.append({hex(section_type): Datum(chunk).d})

                # READ THE AUDIO REFERENCE.
                audio_reference = Datum(chunk).d.chunk_id
                self.chunk_references.append(audio_reference)
                # TODO: Find out what this is and why we have to skip it.
                self.unks.append({hex(section_type): Datum(chunk).d})

                # READ THE VIDEO REFERENCE.
                video_reference = Datum(chunk).d.chunk_id
                self.chunk_references.append(video_reference)
                # TODO: Find out what this is and why we have to skip it.
            else: 
                # READ A SINGLE REFERENCE.
                chunk_reference = Datum(chunk).d.chunk_id
                self.chunk_references.append(chunk_reference)

        elif Asset.SectionType.BOUNDING_BOX == section_type: # STG, IMG, HSP, SPR, MOV, TXT, CAM, CVS
            self.bounding_box = Datum(chunk).d

        elif Asset.SectionType.POLYGON == section_type:
            self.mouse_active_area_polygon = Polygon(chunk)

        elif Asset.SectionType.Z_INDEX == section_type:
            self.z_index = Datum(chunk).d

        elif section_type == Asset.SectionType.ASSET_REFERENCE: # IMG
            # This is the asset ID of the asset that has the same 
            # image/sound data as this asset. For example, in Tonka Garage
            # the asset img_7x51gg009all_GearFourHigh has this field
            # becuase the image in this asset is the same as the image
            # in the asset img_7x51gg009all_GearThreeHigh. 
            # I don't know why they did it this way, as just the chunk
            # reference could have been the same rather than an entire asset reference.
            self.asset_reference = Datum(chunk).d

        elif section_type == 0x001f: # IMG, HSP, SPR, MOV, TXT, CVS
            self.automatically_play = bool(Datum(chunk).d)

        elif section_type == 0x0020: # IMG, SPR, CVS
            # TODO: Determine what this is.
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x0021: # SND, MOV
            self._has_own_subfile = bool(Datum(chunk).d)

        elif section_type == 0x0022: # SCR, TXT, CVS
            # TODO: Determine what this is.
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x0024: # SPR
            # TODO: Determine what this is.
            self.unks.append({hex(section_type): Datum(chunk).d})

        #elif section_type == 0x0026: # TXT
        #    # TODO: This seems to only occur in Ariel.
        #    self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x0032: # IMG, SPR
            # TODO: Determine what this is.
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x0033: # SND, MOV
            # READ THE 
            # These assets are 
            self.total_chunks = Datum(chunk).d
            self.rate = Datum(chunk).d

        elif section_type == 0x0034:
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x0037:
            # TODO: Determine what this is.
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x0258: # TXT
            # This should always be the first entry
            # that defines a text stream.
            self.text = Text.Text()
            self.text.font_asset_id = Datum(chunk).d

        elif section_type == 0x0259: # TXT
            self.text.initial_text = Datum(chunk).d

        elif section_type == 0x025a: # TXT
            self.text.maximum_width_in_pixels = Datum(chunk).d

        elif section_type == 0x025b: # TXT
            self.text.justification = Text.Justification(Datum(chunk).d)

        elif section_type == 0x025f: # TXT
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x0262: # TXT
            pass

        elif section_type == 0x0263:
            pass

        elif section_type == 0x0265: # TXT
            [Datum(chunk) for _ in range(3)]

        elif section_type == 0x0266:
            [Datum(chunk) for _ in range(2)]

        elif section_type >= 0x3a98 and section_type <= 0x3afb:
            self.id = section_type
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x03e8: # SPR
            self.chunks = Datum(chunk).d

        elif section_type == 0x03e9: # SPR
            self.mouse = {"frames": [], "first": None}
            self.mouse["frames"].append(
                {"id": Datum(chunk).d, "x": Datum(chunk).d, "y": Datum(chunk).d}
            )

        elif section_type == 0x03ea: # SPR
            self.mouse["first"] = Datum(chunk).d

        elif section_type == 0x03eb: # IMG, SPR, TXT, CVS
            self.editable = bool(Datum(chunk).d)

        elif section_type == 0x03ec:
            # This should only occur in version 1 games.
            self.cursor = Datum(chunk).d

        elif section_type == 0x03ed:
            # This should only occur in version 1 games.
            # 
            # This type should be only used for LKASB Zazu minigame,
            # so it's okay to hardcode the constant 5.
            self.mouse = {
                "timers": {
                    Datum(chunk).d: [Datum(chunk).d, Datum(chunk).d] for _ in range(5)
                }
            }

        elif section_type == 0x03ee:
            self.mouse.update({"unk": [Datum(chunk).d, Datum(chunk).d]})

        elif section_type == 0x03ef:
            # This should only occur in version 1 games.
            if not self.mouse.get("barriers"):
                self.mouse.update({"barriers": []})

            self.mouse["barriers"].append(Datum(chunk).d)

        elif section_type >= 0x03f0 and section_type <= 0x3f5:
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type >= 0x0514 and section_type < 0x0519:
            # These data are constant across the LKASB constellation
            # minigame. I will ignore them.
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x0519:
            # Same comment as above.
            for _ in range(3):
                self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x05aa: # PAL
            self.palette = chunk.read(0x300)

        elif section_type == 0x05dc:
            # It's only not 0.0 in the 'Read to me' and 'Read and play'
            # images of Dalmatians. So I will ignore it.
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x05dd:
            # I can't find an instance where this isn't 1. So I will ignore it.
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x05de: # IMG
            self.x = Datum(chunk).d

        elif section_type == 0x05df: # IMG
            self.y = Datum(chunk).d

        elif section_type == 0x060e: # PTH
            self.start = [Datum(chunk).d]

        elif section_type == 0x060f: # PTH
            self.end = [Datum(chunk).d]

        elif section_type == 0x0610: # PTH
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x0611: # PTH
            self.end.append(Datum(chunk).d)

        elif section_type == 0x0612: # PTH
            self.start.append(Datum(chunk).d)

        elif section_type == 0x06ac:
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x076f: # CAM
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x0770: # CAM
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x0771: # STG
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x0772: # STG
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x774: # IMAGE_SET
            self.bitmap_count = Datum(chunk).d

        elif section_type == 0x775: # IMAGE_SET
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x776: # IMAGE_SET
            # I think this is just a marker for the beginning of the image set
            # data (0x778s), so I think we can just ignore this.
            self.unks.append({hex(section_type): Datum(chunk).d})
            self.bitmap_declarations = []

        elif section_type == 0x778: # IMAGE_SET
            bitmap_declaration = BitmapSetBitmapDeclaration(chunk)
            self.bitmap_declarations.append(bitmap_declaration)

        elif section_type == 0x779: # IMAGE_SET
            # TODO: Figure out what this is. I just split it out here so I 
            # wouldn't forget about it.
            self.unk_bitmap_set_bounding_box = Datum(chunk).d

        elif section_type >= 0x0773 and section_type <= 0x0780:
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x7d2: # XSND_MIDI (Ariel)
            self.midi_filename = Datum(chunk).d

        elif section_type == 0x7d3:
            probably_asset_id = Datum(chunk).d
            if probably_asset_id != self.id:
                print(f'WARNING: In XSND_MIDI asset, probable asset ID field "{probably_asset_id}" does not match actual asset ID "{self.id}"')

        elif section_type >= 0x07d4 and section_type <= 0x07df: # Ariel
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type >= 0x2734 and section_type <= 0x2800:
            self.unks.append({hex(section_type): Datum(chunk).d})

        elif section_type == 0x0bb8:
            # READ THE ASSET NAME.
            self.name = Datum(chunk).d

        elif section_type == 0x0001: # SND
            self.audio_encoding = Datum(chunk).d

        elif section_type == 0x0002: # SND
            # TODO: Determine what the dfference is between the previous
            # audio encoding section type and this one.
            self.audio_encoding = Datum(chunk).d

        else:
            raise BinaryParsingError(f'Unknown section type: 0x{section_type:0>4x}', chunk.stream)

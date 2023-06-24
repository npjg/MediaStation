A Python-based asset extractor and very incomplete bytecode decompiler for
[Media Station, Inc.](https://www.mobygames.com/company/media-station-inc) CD-ROM children's titles. 
I loved many of these when I was growing up.

Please join me in preserving these top-quality children's titles for future generations!

## Motivation
I re-discovered these titles when I was finding Director titles for the ScummVM Director
engine at GSoC 2020. Coincidentally, the main data file extension (`*.CXT`) used in Media 
Station titles is the same as that used for protected Director cast archives. I quickly
discovered these weren't Director titles but something completely different - and so this
project was born to preserve them.

## Known Titles
If you know of any other titles, please submit a PR to add them here!

| Title                                                                   | Release Year | Engine Version | Supported?        |
|-------------------------------------------------------------------------|--------------|----------------|-------------------|
| Disney's Animated Storybook: The Lion King                              | 1994         | ?              | Yes               |
| Disney's Animated Storybook: Pocahontas                                 | 1995         | ?              | Untested          |
| Disney's Animated Storybook: Winnie the Pooh and the Honey Tree         | 1996         | T3.3           | Untested          |
| Disney's Animated Storybook: The Hunchback of Notre Dame                | 1996         | ?              | Untested          |
| Disney's Toy Story Activity Center                                      | 1996         | ?              | Untested          |
| Disney's Animated Storybook: Toy Story                                  | 1996         | ?              | Untested          |
| Puzzle Castle                                                           | 1996         | ?              | Untested          |
| Jan Pienkowski Haunted House                                            | 1997         | ?              | Untested          |
| Extreme Tactics                                                         | 1997         | ?              | Untested          |
| Disney's Animated Storybook: Hercules                                   | 1997         | ?              | Untested          |
| Disney's Animated Storybook: 101 Dalmatians                             | 1997         | T3.5r5         | Untested          |
| Magic Fairy Tales: Barbie as Rapunzel                                   | 1997         | ?              | Untested          |
| Tonka Search & Rescue                                                   | 1997         | T3.5r5         | Untested          |
| Tonka Garage                                                            | 1998         | T4.0r8         | Yes (no Direct3D) |
| D.W. the Picky Eater                                                    | 1998         | ?              | Untested          |
| Disney presents Ariel's Story Studio                                    | 1999         | ?              | Untested          |
| Tonka Raceway                                                           | 1999         | ?              | Untested          |
| Magic Fairy Tales: Barbie As Rapunzel + Hot Wheels: Custom Car Designer | 2000         | ?              | Untested          |
| Stuart Little: Big City Adventures                                      | 2002         | ?              | Untested          |

## File Formats
All the data files for known titles are stored in the `data/` subdirectory on the CD-ROM. These seem to be the same across the Windows and Mac versions. Some titles have additional files than these (like Tonka Garage, which has some Direct3D models for the car design activity), but these are the known files and formats unique to the Media Station engine.

Media Station titles have these types of files:
 - Context files (`*.CXT`)
 - Title definition file (`BOOT.STM`)
 - Profile (`PROFILE._ST`) - ONLY non-OG titles.

Each context file generally contains all the assets (and, depending on the version, the scripts) necessary to render one screen of the game. Since the format seems to have been originally designed for Disney's Interactive Storybook, this makes sense.

### Context Files
- A _context file_ contains one or more subfiles, which are each complete and (almost) standard `RIFF`s.
- Each _subfile_ inside a context file contains one or more (almost) standard `RIFF` _chunk_s.
  - `igod`: Indicates a chunk that contains metadata about asset(s) in metadata sections.
  - `a000`, where `000` is a string that represents a 3-digit hexadecimal number: Indicates a chunk that contains actual asset data (mainly sounds and bitmaps) with lower-level metadata in metadata sections.
- Each chunk can contain the following:
  - One or more _metadata sections_.
  - Raw asset data (PCM audio or RLE-compressed bitmaps).
- Each metadata section contains one or more _datum_s.
- Each _datum_ contains a "primitive" data type (integer, string, etc.)

### Title Definition (System) File
Also known as the "system" file. Contains metadata sections with global title information like the following:
- Title compiler version.
- Declarations of each context file.
- File offsets of all subfiles in all context files.
- Declarations of cursors stored as resources in the executable.

### Profile
When present, contains a human-readable enumeration of metadata like the following:
 - All the assets in the title, along with the IDs and chunk FourCC(s) for that asset. 
 - Declarations of the variables, constants, cursors, and so forth used in the game.

This doesn't seem to be opened/read by the executables at all while the titles are running.
But there is a ton of useful cross-checking info in here.

## Engine History
Coming soon! For now, the [Disney's Animated Storybook](https://en.wikipedia.org/wiki/Disney%27s_Animated_Storybook) article has great background on the early titles, sourced largely from Newton Lee's books.

## Future Enhancements
- The bytecode decompiler needs a ton of work.
- Some script data seems to be stored in the executables. That should be extracted.
- Write a wikipedia article about the defunct Michigan-based company Media Station, Inc.

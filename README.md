# Media Station

A Python-based asset extractor and very incomplete bytecode decompiler for
[Media Station](https://www.mobygames.com/company/media-station-inc) titles.
I played many of these when I was growing up, and this was the first format
I attempted to reverse engineer while I was bored one semester.

The previous version of this script had a very poor design and was not maintainable,
so I rewrote it pretty much from scratch in 2022 based on some renewed interest 
from the community.

Please join me in preserving these top-quality children's titles for future generations!

## Known Titles
| Title       | Release Year | Engine Version | Tested?     | Extractable? |
| ----------- | -----------  | -----------    | ----------- | -----------  |
| Disney's Animated Storybook: The Lion King | 1994 | OG | No | No |
| Disney's Animated Storybook: Winnie the Pooh and the Honey Tree | 1996 | T3.3 | No | No |
| Disney's Animated Storybook: Pocahontas | 1995 | OG | No | No |
| Disney's Animated Storybook: The Hunchback of Notre Dame | 1996 | OG | No | No |
| Disney's Toy Story Activity Center | 1996 | OG | No | No |
| Disney's Animated Storybook: Toy Story | 1996 | OG | No | No |
| Puzzle Castle | 1996 | OG | No | No |
| Jan Pienkowski Haunted House | 1997 | OG | No | No |
| Extreme Tactics | 1997 | OG | No | No |
| Disney's Animated Storybook: Hercules | 1997 | OG | No | No |
| Disney's Animated Storybook: 101 Dalmatians | 1997 | T3.5r5 | No | No |
| Magic Fairy Tales: Barbie as Rapunzel | 1997 | OG | No | No |
| Tonka Search & Rescue | 1997 | T3.5r5 | No | No |
| Tonka Garage | 1998 | T4.0r8 | No | No |
| D.W. the Picky Eater | 1998 | OG | No | No |
| Disney presents Ariel's Story Studio | 1999 | OG | No | No |
| Tonka Raceway | 1999 | OG | No | No |
| Magic Fairy Tales: Barbie As Rapunzel + Hot Wheels: Custom Car Designer | 2000 | OG | No | No |
| Stuart Little: Big City Adventures | 2002 | OG | No | No |

## Usage


## Engine History
Coming soon!

## File Formats

This file format has a nice organization.
 - A data file contains one or more subfiles, which are each complete and (almost) standard RIFF.
 - Each subfile contains one or more chunks.
 - `igod`: Indicates a chunk that contains metadata
 - `a<i>000</i>`, where `<i>000</i>` is a string that represents a 3-digit hexademical number: Indicates a chunk that contains actual asset data (sounds/images).
 - Each chunk contains one of the following:
   - Raw asset data (PCM audio or RLE-compressed bitmaps)
   - One or more sections.
 - Each section contains one or more datums.
 - Each datum contains a single value (integer, string, etc.)

## TODO: Tighten up my terminology. 
## 
##  - "Chunk" refers to an actual RIFF chunk (designated by FourCC and size).
##  - A series of related datums in a chunk is a "section".

All the data files for known titles are stored in the `data/` subdirectory on the CD-ROM. Each file consists
of one or more subfiles, which each are complete and (almost) standard RIFF. 

### Context
Coincidentally, this extension is the same as that for protected Director cast archives.
I rediscovered these games while I was finding Director titles for the ScummVM Director
engine. Of course, these weren't Director - but I was reminded how much I loved these titles
when I was a kid. 

### System
The "system" file (usually `BOOT.STM`) 

Languages

Data file: Consists of one or more "subfiles". Each subfile is a complete RIFF file.

RIFF
| - IMTSrate
| - LIST
| - data
| - igod
| -- Section type
| -- Value 


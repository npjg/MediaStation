

import pytest
import os
from MediaStation import Engine 

# The directories follow this nomenclature:
#  - Game Title (DW, Dalmatians, etc.)
#  - Title Compiler Version (4.0r8, T3.5r5, etc.)
#  - Platform (PC, Mac)
#  - Language (English, German, etc.)
# This should be sufficient to identify the game.
GAME_ROOT_DIRECTORY = '/Users/nathanaelgentry/My Drive/Software/Media Station'
game_directories = [
    'DW - 4.0r8 - PC - English',
    'Dalmatians - T3.5r5 - Mac - English',
    'Dalmatians - T3.5r5 - PC - English',
    'Hercules - T3.5r5 - PC - English',
    'Lion King - T1.0 - PC - German'
    'Pocahontas - T3.1.1 - PC - German',
    'Pooh - T3.3 - PC - English',
    'Tonka Garage - T4.0r8 - PC - English']

@pytest.mark.parametrize("game_directory_path", game_directories)
def test_process_game(game_directory_path):
    # GET THE FULL GAME DIRECTORY.
    full_game_directory_folder_path = os.path.join(GAME_ROOT_DIRECTORY, game_directory_path)
    print(full_game_directory_folder_path)

    # PARSE THE RESOURCES.
    Engine.main([full_game_directory_folder_path])
    # TODO: Attempt to export the resources (if that is part of the test).

if __name__ == "__main__":
    pytest.main()

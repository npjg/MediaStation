import os

import shutil
import tempfile
import subprocess

import pytest

from MediaStation import Engine 

# Currently, asset export is SLOW because the decompression logic is
# implemented in pure Python, not C. However, bugs are more likely 
# to occur in parsing (as opposed to exporting), so to run tests faster
# we disable asset exporting.
ENABLE_ASSET_EXPORT_IN_TESTS = False

# The tests MUST be run from the root of the repository.
GAME_ROOT_DIRECTORY = 'tests/test_data/Extracted Folders'
game_directories = []
for filename in os.listdir(os.path.realpath(GAME_ROOT_DIRECTORY)):
    filepath = os.path.join(GAME_ROOT_DIRECTORY, filename)
    if os.path.isdir(filepath):
        game_directories.append(filepath)

def test_script_is_runnable():
    # This package includes a command that can be called from the command line,
    # so we will store the name of that script here. It is defined in pyproject.toml,
    # but I didn't see an easy way to reference that here, so we'll just hardcode it.
    CALLABLE_SCRIPT_NAME = 'MediaStation'

    # RUN THE SCRIPT.
    # We shell out rather than just calling the function from Python to make
    # sure that the script entry point is installed correctly too.
    # We don't need to actually process anything, just make sure the script runs.
    # So we can point it to an empty directory.
    empty_directory = tempfile.mkdtemp()
    try:
        # ATTEMPT TO RUN THE SCRIPT.
        command = [CALLABLE_SCRIPT_NAME, empty_directory]
        result = subprocess.run(command, capture_output = True, text = True)            

        # VERIFY THE SCRIPT RAN SUCCESSFULLY.
        if (result.returncode != 0):
            raise AssertionError(
                f'Received a nonzero exit code when running `{CALLABLE_SCRIPT_NAME}` from command line!'
                f'\nstdout: {result.stdout}'
                f'\n\nstderr: {result.stderr}')
    finally:
        shutil.rmtree(empty_directory)

@pytest.mark.parametrize("game_directory_path", game_directories)
def test_process_game(game_directory_path):
    # PARSE THE RESOURCES.
    print(game_directory_path)
    if ENABLE_ASSET_EXPORT_IN_TESTS:
        temp_dir = tempfile.mkdtemp()
        try:
            Engine.main([game_directory_path, '--export', temp_dir])
            # TODO: Do something to verify the integrity of the created files
            # before we delete them.
        finally:
            shutil.rmtree(temp_dir)
    else:
        Engine.main([game_directory_path])

if __name__ == "__main__":
    pytest.main()

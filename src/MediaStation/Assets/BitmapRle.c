#define PY_SSIZE_T_CLEAN
#include <Python.h>

/// Actually decompresses the Media Station RLE stream, and easily provides a 10x performance improvement
/// over the pure Python implementation.
static PyObject *method_decompress_media_station_rle(PyObject *self, PyObject *args) {
    // READ THE PARAMETERS FROM PYTHON.
    PyBytesObject *compressed_image_data_object = NULL;
    unsigned int compressed_image_data_size = 0;
    unsigned int width = 0;
    unsigned int height = 0;
    // `S`: This format unit expects a Python bytes-like object (bytes in Python 3). 
    // Unlike the `s` format unit, which expects a C string (char*), the S format unit 
    // does not allow NULL values and does not handle embedded null bytes. It returns 
    // a new reference to the bytes-like object. 
    if(!PyArg_ParseTuple(args, "SIII", &compressed_image_data_object, &compressed_image_data_size, &width, &height)) {
        // TODO: Need to include errors for all of these returning NULL.
        return NULL;
    }

    // GET THE COMPRESSED PIXELS.
    char *compressed_image_data = NULL;
    compressed_image_data = PyBytes_AsString(compressed_image_data_object);
    if (compressed_image_data == NULL) {
        return NULL;
    }

    // MAKE SURE WE READ PAST THE FIRST 2 BYTES.
    char *compressed_image_data_start = compressed_image_data;
    if ((*compressed_image_data++ == 0) && (*compressed_image_data++ == 0)) {
        // This condition is empty, we just put it first since this is the expected case
        // and the negated logic would be not as readable.
    } else {
        compressed_image_data = compressed_image_data_start;
    }

    // ALLOCATE THE DECOMPRESSED PIXELS BUFFER.
    unsigned int uncompressed_image_data_size = width * height;
    char *uncompressed_image_data = calloc(uncompressed_image_data_size + 1, 1);
    if (uncompressed_image_data == NULL) {
        return NULL;
    }

    // CREATE THE LIST TO HOLD THE TRANSPARENCY REGIONS.
    // This would be better to do in Python, but since it's part of the compressed stream 
    // we'll just do it here. It's a good learning experience anyway.
    PyObject *transparency_regions_list;
    transparency_regions_list = PyList_New(0);
    if (transparency_regions_list == NULL) {
        return NULL;
    }

    // CHECK FOR AN EMPTY COMPRESSED IMAGE.
    if (compressed_image_data_size <= 2) {
        // RETURN A BLANK IMAGE TO PYTHON.
        PyObject *return_value = Py_BuildValue("(y#O)", uncompressed_image_data, uncompressed_image_data_size, transparency_regions_list);
        free(uncompressed_image_data);
        return return_value;
    }

    // DECOMPRESS THE RLE-COMPRESSED BITMAP STREAM.
    size_t transparency_run_row_index = 0;
    size_t transparency_run_start_horizontal_pixel_offset = 0;
    int image_fully_read = 0;
    size_t row_index = 0;
    while (row_index < height) {
        size_t horizontal_pixel_offset = 0;
        int reading_transparency_run = 0;
        while (1) {
            uint8_t operation = *compressed_image_data++;
            if (operation == 0x00) {
                // ENTER CONTROL MODE.
                operation = *compressed_image_data++;
                if (operation == 0x00) {
                    // MARK THE END OF THE LINE.
                    break;
                } else if (operation == 0x01) {
                    // MARK THE END OF THE IMAGE.
                    // TODO: When is this actually used?
                    image_fully_read = 1;
                    break;
                } else if (operation == 0x02) {
                    // MARK THE START OF A KEYFRAME TRANSPARENCY REGION.
                    // Until a color index other than 0x00 (usually white) is read on this line,
                    // all pixels on this line will be marked transparent.
                    // If no transparency regions are present in this image, all 0x00 color indices are treated
                    // as transparent. Otherwise, only the 0x00 color indices within transparency regions
                    // are considered transparent. Only intraframes (frames that are not keyframes) have been
                    // observed to have transparency regions, and these intraframes have them so the keyframe
                    // can extend outside the boundary of the intraframe and still be removed.
                    reading_transparency_run = 1;
                    transparency_run_row_index = row_index;
                    transparency_run_start_horizontal_pixel_offset = horizontal_pixel_offset;
                } else if (operation == 0x03) {
                    // ADJUST THE PIXEL POSITION.
                    // This permits jumping to a different part of the same row without
                    // needing a run of pixels in between. But the actual data consumed
                    // seems to actually be higher this way, as you need the control byte
                    // first.
                    // So to skip 10 pixels using this approach, you would encode 00 03 0a 00.
                    // But to "skip" 10 pixels by encoding them as blank (0xff), you would encode 0a ff.
                    // What gives? I'm not sure.
                    uint8_t x_change = *compressed_image_data++;
                    horizontal_pixel_offset += x_change;
                    uint8_t y_change = *compressed_image_data++;
                    row_index += y_change;
                } else if (operation >= 0x04) {
                    // READ A RUN OF UNCOMPRESSED PIXELS.
                    size_t vertical_pixel_offset = row_index * width;
                    size_t run_starting_offset = vertical_pixel_offset + horizontal_pixel_offset;
                    memcpy(uncompressed_image_data + run_starting_offset, compressed_image_data, operation);

                    compressed_image_data += operation;
                    horizontal_pixel_offset += operation;

                    if (((uintptr_t)compressed_image_data) % 2 == 1) {
                        compressed_image_data++;
                    }
                }
            } else {
                // READ A RUN OF LENGTH ENCODED PIXELS.
                size_t vertical_pixel_offset = row_index * width;
                size_t run_starting_offset = vertical_pixel_offset + horizontal_pixel_offset;
                uint8_t color_index_to_repeat = *compressed_image_data++;
                uint8_t repetition_count = operation;

                // TODO: Can we use memset for this instead?
                for (size_t i = 0; i < repetition_count; i++) {
                    uncompressed_image_data[run_starting_offset + i] = color_index_to_repeat;
                }

                horizontal_pixel_offset += repetition_count;

                if (reading_transparency_run) {
                    // MARK THIS PART OF THE TRANSPARENCY REGION.
                    // At first, I tried to create a bitmap mask using code like the following:
                    //
                    // I did this becuase it would be more straightforward to apply the transparency
                    // rather than using this list of transparency regions. This fell apart when I 
                    // realized that in movied that DON'T have transparency regions, all white pixels
                    // (usually 0x00) should be treated as transparent. That added a bit more complexity
                    // than I wanted to deal with at the moment, as well as the added overhead of managing
                    // and applying animation framing to a masked bitmap.
                    //
                    // The "interior" of transparency regions is always encoded by a single run of
                    // pixels, usually 0x00 (white).
                    PyObject *transparency_run_tuple = Py_BuildValue("(nnn)", transparency_run_row_index, transparency_run_start_horizontal_pixel_offset, operation);
                    if (transparency_run_tuple == NULL) {
                        return NULL;
                    }
                    // Now we append to the list.
                    if (PyList_Append(transparency_regions_list, transparency_run_tuple) != 0) {
                        return NULL;
                    }
                    reading_transparency_run = 0;
                }
            }
        }

        row_index++;
        if (image_fully_read) {
            break;
        }
    }

    // RETURN THE DECOMPRESSED PIXELS TO PYTHON.
    PyObject *return_value = Py_BuildValue("(y#O)", uncompressed_image_data, uncompressed_image_data_size, transparency_regions_list);
    if (return_value == NULL) {
        return NULL;
    }

    // FREE THE DECOMPRESSED PIXELS.
    free(uncompressed_image_data);
    return return_value;
}

/// Defines the Python methods callable in this module.
static PyMethodDef MediaStationBitmapRleDecompressionMethod[] = {
    {"decompress", method_decompress_media_station_rle, METH_VARARGS, "Decompresses raw Media Station RLE-encoded streams into an image bitmap (8-bit indexed color) and a transparency bitmap (monochrome, but still 8-bit for simplicity)."},
    // An entry of nulls must be provided to indicate we're done.
    {NULL, NULL, 0, NULL}
};

/// Defines the Python module itself. Because the module requires references to 
/// each of the methods, the module must be defined after the methods.
static struct PyModuleDef MediaStationBitmapRleModule = {
    PyModuleDef_HEAD_INIT,
    "BitmapRle",
    "Python interface for interacting with raw Media Station RLE-encoded streams. Currently only decompression is supported.",
    // A negative value indicates that this module doesn’t have support for sub-interpreters.
    // A non-negative value enables the re-initialization of your module. It also specifies 
    // the memory requirement of your module to be allocated on each sub-interpreter session.
    -1,
    MediaStationBitmapRleDecompressionMethod
};

/// Called when a Python script inputs this module for the first time.
PyMODINIT_FUNC PyInit_MediaStationBitmapRle(void) {
    return PyModule_Create(&MediaStationBitmapRleModule);
}

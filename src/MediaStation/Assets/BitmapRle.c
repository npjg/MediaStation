#define PY_SSIZE_T_CLEAN
#include <Python.h>

/// Actually decompresses the Media Station RLE stream, and easily provides a 10x performance improvement
/// over the pure Python implementation.
static PyObject *method_decompress_media_station_rle(PyObject *self, PyObject *args) {
    // READ THE PARAMETERS FROM PYTHON.
    char *compressed_image;
    Py_ssize_t compressed_image_data_size_in_bytes;
    unsigned int width = 0;
    unsigned int height = 0;
    // `S`: This format unit expects a Python bytes-like object (bytes in Python 3). 
    // Unlike the `s` format unit, which expects a C string (char*), the S format unit 
    // does not allow NULL values and does not handle embedded null bytes. It returns 
    // a new reference to the bytes-like object. 
    if(!PyArg_ParseTuple(args, "y#II", &compressed_image, &compressed_image_data_size_in_bytes, &width, &height)) {
        PyErr_Format(PyExc_RuntimeError, "BitmapRle.c::PyArg_ParseTuple(): Failed to parse arguments.");
        return NULL;
    }

    // MAKE SURE WE READ PAST THE FIRST 2 BYTES.
    char *compressed_image_data_start = compressed_image;
    if ((*compressed_image++ == 0) && (*compressed_image++ == 0)) {
        // This condition is empty, we just put it first since this is the expected case
        // and the negated logic would be not as readable.
    } else {
        compressed_image = compressed_image_data_start;
    }

    // ALLOCATE THE DECOMPRESSED PIXELS BUFFER.
    // Media Station has 8 bits per pixel, so the decompression buffer is simple.
    unsigned int uncompressed_image_data_size_in_bytes = width * height;
    PyObject *decompressed_image_object = PyBytes_FromStringAndSize(NULL, uncompressed_image_data_size_in_bytes);
    if (decompressed_image_object == NULL) {
        // TODO: We really should use Py_DECREF here I think, but since the
        // program will currently just quit it isn't a big deal.
        PyErr_Format(PyExc_RuntimeError, "BitmapRle.c: Failed to allocate decompressed image data buffer.");
        return NULL;
    }
    char *decompressed_image = PyBytes_AS_STRING(decompressed_image_object);
    // Clear the bitmap canvas, so there's no random data in 
    // places we don't actually write pixels to.
    memset(decompressed_image, 0x00, uncompressed_image_data_size_in_bytes);

    // CREATE THE LIST TO HOLD THE TRANSPARENCY REGIONS.
    // This would be better to do in Python, but since it's part of the compressed stream 
    // we'll just do it here. It's a good learning experience anyway.
    PyObject *transparency_regions_list;
    transparency_regions_list = PyList_New(0);
    if (transparency_regions_list == NULL) {
        PyErr_Format(PyExc_RuntimeError, "BitmapRle.c::PyList_New(): Failed to allocate transparency regions list.");
        return NULL;
    }

    // CHECK FOR AN EMPTY COMPRESSED IMAGE.
    if (compressed_image_data_size_in_bytes <= 2) {
        // RETURN A BLANK IMAGE TO PYTHON.
        PyObject *return_value = Py_BuildValue("(OO)", decompressed_image_object, transparency_regions_list);
        // Decrease the reference counts, as Py_BuildValue increments them.
        Py_DECREF(decompressed_image_object);
        Py_DECREF(transparency_regions_list);
        if (return_value == NULL) {
            PyErr_Format(PyExc_RuntimeError, "BitmapRle.c::Py_BuildValue(): Failed to build return value.");
            return NULL;
        }
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
            uint8_t operation = *compressed_image++;
            if (operation == 0x00) {
                // ENTER CONTROL MODE.
                operation = *compressed_image++;
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
                    uint8_t x_change = *compressed_image++;
                    horizontal_pixel_offset += x_change;
                    uint8_t y_change = *compressed_image++;
                    row_index += y_change;
                } else if (operation >= 0x04) {
                    // READ A RUN OF UNCOMPRESSED PIXELS.
                    size_t vertical_pixel_offset = row_index * width;
                    size_t run_starting_offset = vertical_pixel_offset + horizontal_pixel_offset;
                    memcpy(decompressed_image + run_starting_offset, compressed_image, operation);

                    compressed_image += operation;
                    horizontal_pixel_offset += operation;

                    if (((uintptr_t)compressed_image) % 2 == 1) {
                        compressed_image++;
                    }
                }
            } else {
                // READ A RUN OF LENGTH ENCODED PIXELS.
                size_t vertical_pixel_offset = row_index * width;
                size_t run_starting_offset = vertical_pixel_offset + horizontal_pixel_offset;
                uint8_t color_index_to_repeat = *compressed_image++;
                uint8_t repetition_count = operation;
                memset(decompressed_image + run_starting_offset, color_index_to_repeat, repetition_count);
                horizontal_pixel_offset += repetition_count;

                if (reading_transparency_run) {
                    // MARK THIS PART OF THE TRANSPARENCY REGION.
                    // TODO: Actually return the transparency in a region we can
                    // use. Or maybe the transparency can actually be applied
                    // right here?
                    // At first, I tried to create a bitmap mask for
                    // transparency, like this:
                    //     if (reading_transparency_run) {
                    //     // MARK THE TRANSPARENCY REGION.
                    //     // The "interior" of transparency regions is always encoded by a single run of
                    //     // pixels, usually 0x00 (white).
                        
                    //     // GET THE TRANSPARENCY RUN STARTING OFFSET.
                    //     size_t transparency_run_start_vertical_pixel_offset = transparency_run_row_index * width;
                    //     size_t transparency_run_starting_offset = transparency_run_start_vertical_pixel_offset + transparency_run_start_horizontal_pixel_offset;

                    //     // GET THE TRANSPARENCY RUN ENDING OFFSET.
                    //     size_t vertical_pixel_offset = row_index * width;
                    //     // This is where we are right now.
                    //     size_t transparency_run_ending_offset = vertical_pixel_offset + horizontal_pixel_offset;

                    //     // GET THE NUMBER OF PIXELS (BYTES) IN THE TRANSPARENCY RUN.
                    //     // This could be optimized using a bitfield, since the transparency mask is monochrome, but that isn't
                    //     // worth it right now.
                    //     size_t transparency_run_length = transparency_run_ending_offset - transparency_run_starting_offset;
                    //     memset(transparency_mask + run_starting_offset, 0xff, transparency_run_length);
                    //     reading_transparency_run = 0;
                    // }
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
                    PyObject *transparency_run_tuple = Py_BuildValue("(nnn)", transparency_run_start_horizontal_pixel_offset, transparency_run_row_index, operation);
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
    // TODO: Can we use `PyBytes_FromStringAndSize` to be more self-documenting?
    PyObject *return_value = Py_BuildValue("(OO)", decompressed_image_object, transparency_regions_list);
    // Decrease the reference counts, as Py_BuildValue increments them.
    Py_DECREF(decompressed_image_object);
    Py_DECREF(transparency_regions_list);
    if (return_value == NULL) {
        PyErr_Format(PyExc_RuntimeError, "BitmapRle.c::Py_BuildValue(): Failed to build return value.");
        return NULL;
    }
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

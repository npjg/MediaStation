#define PY_SSIZE_T_CLEAN
#include <Python.h>

/// Actually decompresses the Media Station RLE stream, and easily provides a 10x performance improvement
/// over the pure Python implementation.
static PyObject *method_decompress_media_station_rle(PyObject *self, PyObject *args) {
    // READ THE PARAMETERS FROM PYTHON.
    char *compressed_image;
    Py_ssize_t compressed_image_data_size_in_bytes;
    // The width and height of this particular frame.
    unsigned int frame_width = 0;
    unsigned int frame_height = 0;
    // The width and height of the animation that this frame is part of (if
    // applicable).
    unsigned int full_width = 0;
    unsigned int full_height = 0;
    // The X and Y coordinates of the frame inside the animation width and
    // height (if applicable).
    unsigned int frame_left_x_coordinate = 0;
    unsigned int frame_top_y_coordinate = 0;
    // The keyframe that we want to apply to this image.
    // It is expected to be the same size as the uncompressed image.
    char *keyframe_image = NULL;
    Py_ssize_t keyframe_image_size_in_bytes = 0;
    if(!PyArg_ParseTuple(args, "y#II|IIIIy#", &compressed_image, &compressed_image_data_size_in_bytes, &frame_width, &frame_height, &full_width, &full_height, &frame_left_x_coordinate, &frame_top_y_coordinate, &keyframe_image, &keyframe_image_size_in_bytes)) {
        PyErr_Format(PyExc_RuntimeError, "BitmapRle.c::PyArg_ParseTuple(): Failed to parse arguments.");
        return NULL;
    }
    if (keyframe_image_size_in_bytes == 0) {
        keyframe_image = NULL;
    }

    // MAKE SURE THE PARAMETERS ARE SAME.
    // The full width and full height are optional, so if they are not provided
    // assume the full width and height is the same as the width and height for 
    // this specific bitmap.
    if (full_width == 0) {
        full_width = frame_width;
    }
    if (full_height == 0) {
        full_height = frame_height;
    }
    // Verify that with the coordinates specified, we don't overflow the
    // space alloted for the frame.
    if (frame_left_x_coordinate + frame_width > full_width) {
        PyErr_Format(PyExc_RuntimeError, "BitmapRle.c: frame_left_x_coordinate (%u) + frame_width (%u) > full_width (%u)", frame_left_x_coordinate, frame_width, full_width);
        return NULL;
    }
    if (frame_top_y_coordinate + frame_height > full_height) {
        PyErr_Format(PyExc_RuntimeError, "BitmapRle.c: frame_top_y_coordinate (%u) + frame_height (%u) > full_height (%u)", frame_top_y_coordinate, frame_height, full_height);
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
    char *compressed_image_data_end = compressed_image + compressed_image_data_size_in_bytes;

    // ALLOCATE THE DECOMPRESSED PIXELS BUFFER.
    // Media Station has 8 bits per pixel, so the decompression buffer is simple.
    unsigned int uncompressed_image_data_size_in_bytes = full_width * full_height;
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

    // MAKE SURE THE KEYFRAME IMAGE IS THE RIGHT SIZE.
    if (keyframe_image != NULL) {
        if (keyframe_image_size_in_bytes != uncompressed_image_data_size_in_bytes) {
            PyErr_Format(PyExc_RuntimeError, "BitmapRle.c: keyframe_image_size_in_bytes (%u) != uncompressed_image_data_size_in_bytes (%u)", keyframe_image_size_in_bytes, uncompressed_image_data_size_in_bytes);
            return NULL;
        }
    }

    // DECOMPRESS THE RLE-COMPRESSED BITMAP STREAM.
    int transparency_run_ever_read = 0;
    size_t transparency_run_top_y_coordinate = 0;
    size_t transparency_run_left_x_coordinate = 0;
    int image_fully_read = 0;
    size_t current_y_coordinate = frame_top_y_coordinate;
    while (current_y_coordinate < frame_top_y_coordinate + frame_height) {
        size_t current_x_coordinate = frame_left_x_coordinate;
        int reading_transparency_run = 0;
        while (1) {
            uint8_t operation = *compressed_image++;
            if (operation == 0x00) {
                // ENTER CONTROL MODE.
                operation = *compressed_image++;
                if (operation == 0x00) {
                    // MARK THE END OF THE LINE.
                    // Also check if the image is finished being read.
                    if (compressed_image >= compressed_image_data_end) {
                        image_fully_read = 1;
                    }
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
                    // can extend outside the boundary of the intraframe and
                    // still be removed.
                    if (keyframe_image != NULL) {
                        reading_transparency_run = 1;
                        transparency_run_top_y_coordinate = current_y_coordinate;
                        transparency_run_left_x_coordinate = current_x_coordinate;
                        transparency_run_ever_read = 1;
                    } else {
                        // printf("WARNING: BitmapRle.c: Found transparency region, but no keyframe is provided. Transparency region will be ignored.\n");
                    }
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
                    current_x_coordinate += x_change;
                    uint8_t y_change = *compressed_image++;
                    current_y_coordinate += y_change;
                } else if (operation >= 0x04) {
                    // READ A RUN OF UNCOMPRESSED PIXELS.
                    size_t y_offset = current_y_coordinate * full_width;
                    size_t run_starting_offset = y_offset + current_x_coordinate;
                    char* run_starting_pointer = decompressed_image + run_starting_offset;
                    uint8_t run_length = operation;
                    memcpy(run_starting_pointer, compressed_image, run_length);
                    compressed_image += operation;
                    current_x_coordinate += operation;

                    if (((uintptr_t)compressed_image) % 2 == 1) {
                        compressed_image++;
                    }
                }
            } else {
                // READ A RUN OF LENGTH ENCODED PIXELS.
                size_t y_offset = current_y_coordinate * full_width;
                size_t run_starting_offset = y_offset + current_x_coordinate;
                char *run_starting_pointer = decompressed_image + run_starting_offset;
                uint8_t color_index_to_repeat = *compressed_image++;
                uint8_t repetition_count = operation;
                memset(run_starting_pointer, color_index_to_repeat, repetition_count);
                current_x_coordinate += repetition_count;

                if (reading_transparency_run) {
                    // GET THE TRANSPARENCY RUN STARTING OFFSET.
                    size_t transparency_run_y_offset = transparency_run_top_y_coordinate * full_width;
                    size_t transparency_run_start_offset = transparency_run_y_offset + transparency_run_left_x_coordinate;
                    size_t transparency_run_ending_offset = y_offset + current_x_coordinate;
                    size_t transparency_run_length = transparency_run_ending_offset - transparency_run_start_offset;
                    char *transparency_run_src_pointer = keyframe_image + run_starting_offset;
                    char *transparency_run_dest_pointer = decompressed_image + run_starting_offset;

                    // COPY THE TRANSPARENT AREA FROM THE KEYFRAME.
                    // The "interior" of transparency regions is always encoded by a single run of
                    // pixels, usually 0x00 (white).
                    memcpy(transparency_run_dest_pointer, transparency_run_src_pointer, transparency_run_length);
                    reading_transparency_run = 0;
                }
            }
        }

        current_y_coordinate++;
        if (image_fully_read) {
            break;
        }
    }

    // APPLY THE KEYFRAME TO THE DECOMPRESSED IMAGE.
    if (keyframe_image != NULL && transparency_run_ever_read == 0) {
        for (size_t i = 0; i < uncompressed_image_data_size_in_bytes; i++) {
            if (decompressed_image[i] == 0x00) {
                decompressed_image[i] = keyframe_image[i];
            }
        }
    }

    // RETURN THE FRAMED BITMAP TO PYTHON.
    return decompressed_image_object;
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

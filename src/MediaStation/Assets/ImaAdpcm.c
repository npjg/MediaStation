#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
 
// IMA ADPCM decoding tables
static int ima_index_table[16] = {
    -1, -1, -1, -1, 2, 4, 6, 8,
    -1, -1, -1, -1, 2, 4, 6, 8
};
 
static int ima_step_table[89] = {
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17,
    19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
    130, 143, 157, 173, 190, 209, 230, 253, 279, 307,
    337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
    876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
    2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358,
    5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899,
    15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
};
 
// Decode IMA ADPCM samples to raw PCM
static PyObject* decode(PyObject* self, PyObject* args) {
    // READ THE PARAMETERS FROM PYTHON.
    PyBytesObject *ima_data_object = NULL;
    unsigned int ima_data_len = 0;
     // `S`: This format unit expects a Python bytes-like object (bytes in Python 3). 
    if (!PyArg_ParseTuple(args, "SI", &ima_data_object, &ima_data_len)) {
        return NULL;
    }

    // GET THE COMPRESSED DATA.
    char *ima_data_ptr = NULL;
    ima_data_ptr = PyBytes_AsString(ima_data_object);

    // ALLOCATE MEMORY FOR THE RAW PCM SAMPLES.
    // TODO: Is this allocation size correct? Seems a bit wrong.
    int pcm_data_len = ima_data_len * 2; // 16-bit (2 bytes) per sample
    int16_t* pcm_data_ptr = (int16_t*)malloc(pcm_data_len);
    if (pcm_data_ptr == NULL) {
        PyErr_NoMemory();
        return NULL;
    }
 
    // DECOMPRESS THE IMA ADPCM SAMPLES TO RAW PCM.
    int predictor = 0;
    int step_index = 0;
    int step = ima_step_table[step_index];
    for (int i = 0; i < ima_data_len; i += 2) {
        uint8_t nibble = ima_data_ptr[i / 2] >> (i % 2 == 0 ? 0 : 4);
        step_index = (step_index + ima_index_table[nibble]) & 0x7F;
        step = ima_step_table[step_index];
        int diff = ((int)nibble + 0.5) * step / 4;
        predictor = (predictor + diff) & 0xFFFF;
        pcm_data_ptr[i / 2] = predictor;
    }
 
    // RETURN THE RAW PCM TO PYTHON.
    PyObject* pcm_data_bytes = PyBytes_FromStringAndSize((const char*)pcm_data_ptr, pcm_data_len);
    if (pcm_data_bytes == NULL) {
        return NULL;
    }

    // FREE THE RAW PCM.
    free(pcm_data_ptr);
    return pcm_data_bytes;
}
 
static PyMethodDef MediaStationImaAdpcmDecompressionMethod[] = {
    {
        "decode", 
        decode, 
        METH_VARARGS,
        "Decompresses raw IMA ADPCM samples to raw PCM"
    },
    {NULL, NULL, 0, NULL}
};
 
static struct PyModuleDef MediaStationImaAdpcmModule = {
    PyModuleDef_HEAD_INIT,
    "ImaAdpcm",
    "IMA ADPCM decoding module",
    -1,
    MediaStationImaAdpcmDecompressionMethod
};
 
PyMODINIT_FUNC PyInit_MediaStationImaAdpcm(void) {
    return PyModule_Create(&MediaStationImaAdpcmModule);
}
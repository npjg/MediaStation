#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>

// Most of the code in this file is borrowed from SoX,
// specifically sox/src/adpcms.c, which is licensed
// under the GPL.

 static int const ima_steps[89] = {
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230,
    253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963,
    1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327,
    3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442,
    11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794,
    32767
};

static int const step_changes[8] = {-1, -1, -1, -1, 2, 4, 6, 8};

typedef struct {
    int max_step_index;
    int sign;
    int shift;
    int const *steps;
    int const *changes;
    int mask;
} adpcm_setup_t;

typedef struct {
    adpcm_setup_t setup;
    int last_output;
    int step_index;
} adpcm_t;

static adpcm_setup_t const setup_ima = {88, 8, 2, ima_steps, step_changes, ~0};

void lsx_adpcm_init(adpcm_t *p, int first_sample)
{
    p->setup = setup_ima;
    p->last_output = first_sample;
    p->step_index = 0;
}

#define min_sample -0x8000
#define max_sample 0x7fff

int lsx_adpcm_decode(int code, adpcm_t *p)
{
    int s = ((code & (p->setup.sign - 1)) << 1) | 1;
    s = ((p->setup.steps[p->step_index] * s) >> (p->setup.shift + 1)) & p->setup.mask;
    if (code & p->setup.sign)
        s = -s;
    s += p->last_output;
    if (s < min_sample || s > max_sample) {
        s = s < min_sample ? min_sample : max_sample;
    }
    p->step_index += p->setup.changes[code & (p->setup.sign - 1)];
    if (p->step_index < 0) p->step_index = 0;
    if (p->step_index > p->setup.max_step_index) p->step_index = p->setup.max_step_index;
    return p->last_output = s;
}
 
static PyObject* decode(PyObject* self, PyObject* args) {
    const char *input;
    Py_ssize_t input_length;
    if (!PyArg_ParseTuple(args, "y#", &input, &input_length))
        return NULL;

    adpcm_t adpcm;
    lsx_adpcm_init(&adpcm, 0);

    PyObject *output = PyBytes_FromStringAndSize(NULL, input_length * 4);
    int16_t *output_buffer = (int16_t *)PyBytes_AS_STRING(output);

    for (Py_ssize_t i = 0; i < input_length; ++i) {
        int byte = input[i];
        *output_buffer++ = lsx_adpcm_decode(byte >> 4, &adpcm);
        *output_buffer++ = lsx_adpcm_decode(byte & 0xF, &adpcm);
    }

    return output;
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
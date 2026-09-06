/* fb_fast — C fast path for FrameBuffer.append (SoA field writes).
 *
 * numpy scalar/row __setitem__ ~0.2-0.8us per field; 17 assignments per
 * sprite ~ 3-4us in Python. This module binds the buffer-protocol views
 * ONCE per FrameBuffer (capsule), then fb_append writes all fields via
 * raw pointers (~0.5us total per sprite).
 *
 * Buffers are treated as fixed-capacity (FrameBuffer never reallocates
 * its arrays after __init__), so the views are safe to hold for the
 * lifetime of the capsule. The numpy fallback still exists in
 * frame_buffer.py when this module is unavailable.
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdint.h>
#include <string.h>

#define FB_VIEWS_NAME "plyunit.fb_views"
#define FB_N_ARRAYS 14

typedef struct {
    Py_buffer b[FB_N_ARRAYS];
    Py_ssize_t capacity;
} FbViews;

static void fb_release(FbViews *v)
{
    for (int k = 0; k < FB_N_ARRAYS; k++) {
        if (v->b[k].obj != NULL) {
            PyBuffer_Release(&v->b[k]);
            v->b[k].obj = NULL;
        }
    }
}

static void fb_capsule_free(PyObject *cap)
{
    FbViews *v = (FbViews *)PyCapsule_GetPointer(cap, FB_VIEWS_NAME);
    if (v != NULL) {
        fb_release(v);
        PyMem_Free(v);
    }
}

/* fb_bind_buffers(pos, size, origin, rot, rgba, uv, tex, sort, layer,
 *                 state, pass, submit, depth, screen, capacity) -> capsule
 *
 * The array order must exactly match the FieldBuffer SoA; dtype is
 * validated via buffer length (bytes) vs capacity.
 */
static PyObject *py_fb_bind(PyObject *self, PyObject *args)
{
    PyObject *objs[FB_N_ARRAYS];
    FbViews *v;
    PyObject *cap;
    Py_ssize_t capacity;

    /* minimal length (bytes) per array for `capacity` sprites */
    static const Py_ssize_t min_item_bytes[FB_N_ARRAYS] = {
        2 * 4, /* pos_xy   float32 x2 */
        2 * 4, /* size_wh  float32 x2 */
        2 * 4, /* origin   float32 x2 */
        4,     /* rot      float32 */
        4,     /* rgba     uint8  x4 */
        4 * 4, /* uv       float32 x4 */
        4,     /* tex_id   int32 */
        4,     /* sort_key float32 */
        4,     /* layer    int32 */
        4,     /* state_id int32 */
        4,     /* pass_hash int32 */
        4,     /* submit_index int32 */
        1,     /* depth_sorted bool */
        1,     /* screen_space bool */
    };

    (void)self;
    if (!PyArg_ParseTuple(
            args,
            "OOOOOOOOOOOOOOn",
            &objs[0], &objs[1], &objs[2], &objs[3], &objs[4], &objs[5],
            &objs[6], &objs[7], &objs[8], &objs[9], &objs[10], &objs[11],
            &objs[12], &objs[13],
            &capacity)) {
        return NULL;
    }
    if (capacity <= 0) {
        PyErr_SetString(PyExc_ValueError, "capacity must be > 0");
        return NULL;
    }

    v = PyMem_Calloc(1, sizeof(FbViews));
    if (v == NULL) {
        return PyErr_NoMemory();
    }
    for (int k = 0; k < FB_N_ARRAYS; k++) {
        if (PyObject_GetBuffer(objs[k], &v->b[k], PyBUF_WRITABLE) < 0) {
            fb_release(v);
            PyMem_Free(v);
            return NULL;
        }
        if (v->b[k].len < capacity * min_item_bytes[k]) {
            PyErr_Format(
                PyExc_ValueError,
                "fb buffer #%d too small: %zd bytes < %zd needed",
                k,
                (Py_ssize_t)v->b[k].len,
                capacity * min_item_bytes[k]);
            fb_release(v);
            PyMem_Free(v);
            return NULL;
        }
    }
    v->capacity = capacity;

    cap = PyCapsule_New(v, FB_VIEWS_NAME, fb_capsule_free);
    if (cap == NULL) {
        fb_release(v);
        PyMem_Free(v);
        return NULL;
    }
    return cap;
}

/* fb_append(views, index, px, py, sw, sh, ox, oy, rot, r, g, b, a,
 *           u0, u1, u2, u3, tex_id, sort_key, layer, state_id,
 *           pass_hash, submit_index, depth_sorted, screen_space)
 *
 * METH_FASTCALL positional-only: 25 args. All scalar conversion via
 * PyFloat_AsDouble / PyLong_AsLong / PyObject_IsTrue.
 */
static PyObject *py_fb_append(PyObject *self, PyObject *const *args, Py_ssize_t nargs)
{
    FbViews *v;
    Py_ssize_t i;
    float *pos, *size, *origin, *rot, *uv, *sort;
    uint8_t *rgba, *depth, *screen;
    int32_t *tex, *layer, *state, *pass, *submit;

    (void)self;
    if (nargs != 25) {
        PyErr_Format(PyExc_TypeError, "fb_append expects 25 args, got %zd", nargs);
        return NULL;
    }
    v = (FbViews *)PyCapsule_GetPointer(args[0], FB_VIEWS_NAME);
    if (v == NULL) {
        return NULL;
    }
    i = PyLong_AsSsize_t(args[1]);
    if (i < 0 || i >= v->capacity) {
        if (!PyErr_Occurred()) {
            PyErr_Format(PyExc_IndexError, "fb_append index %zd out of range", i);
        }
        return NULL;
    }

    pos = (float *)v->b[0].buf;
    size = (float *)v->b[1].buf;
    origin = (float *)v->b[2].buf;
    rot = (float *)v->b[3].buf;
    rgba = (uint8_t *)v->b[4].buf;
    uv = (float *)v->b[5].buf;
    tex = (int32_t *)v->b[6].buf;
    sort = (float *)v->b[7].buf;
    layer = (int32_t *)v->b[8].buf;
    state = (int32_t *)v->b[9].buf;
    pass = (int32_t *)v->b[10].buf;
    submit = (int32_t *)v->b[11].buf;
    depth = (uint8_t *)v->b[12].buf;
    screen = (uint8_t *)v->b[13].buf;

    pos[i * 2] = (float)PyFloat_AsDouble(args[2]);
    pos[i * 2 + 1] = (float)PyFloat_AsDouble(args[3]);
    size[i * 2] = (float)PyFloat_AsDouble(args[4]);
    size[i * 2 + 1] = (float)PyFloat_AsDouble(args[5]);
    origin[i * 2] = (float)PyFloat_AsDouble(args[6]);
    origin[i * 2 + 1] = (float)PyFloat_AsDouble(args[7]);
    rot[i] = (float)PyFloat_AsDouble(args[8]);
    rgba[i * 4] = (uint8_t)PyLong_AsLong(args[9]);
    rgba[i * 4 + 1] = (uint8_t)PyLong_AsLong(args[10]);
    rgba[i * 4 + 2] = (uint8_t)PyLong_AsLong(args[11]);
    rgba[i * 4 + 3] = (uint8_t)PyLong_AsLong(args[12]);
    uv[i * 4] = (float)PyFloat_AsDouble(args[13]);
    uv[i * 4 + 1] = (float)PyFloat_AsDouble(args[14]);
    uv[i * 4 + 2] = (float)PyFloat_AsDouble(args[15]);
    uv[i * 4 + 3] = (float)PyFloat_AsDouble(args[16]);
    tex[i] = (int32_t)PyLong_AsLong(args[17]);
    sort[i] = (float)PyFloat_AsDouble(args[18]);
    layer[i] = (int32_t)PyLong_AsLong(args[19]);
    state[i] = (int32_t)PyLong_AsLong(args[20]);
    pass[i] = (int32_t)PyLong_AsLong(args[21]);
    submit[i] = (int32_t)PyLong_AsLong(args[22]);
    depth[i] = (uint8_t)PyObject_IsTrue(args[23]);
    screen[i] = (uint8_t)PyObject_IsTrue(args[24]);

    if (PyErr_Occurred()) {
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"fb_bind_buffers", py_fb_bind, METH_VARARGS,
     "Bind 14 SoA buffers (+capacity) into a capsule of writable views."},
    {"fb_append", (PyCFunction)(void (*)(void))py_fb_append, METH_FASTCALL,
     "Write one sprite's SoA fields via raw pointers (positional-only, 25 args)."},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "plyunit._fb_fast",
    "plyunit FrameBuffer C fast path",
    -1,
    methods,
    NULL,
    NULL,
    NULL,
    NULL,
};

PyMODINIT_FUNC PyInit__fb_fast(void)
{
    return PyModule_Create(&moduledef);
}

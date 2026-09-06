#define PY_SSIZE_T_CLEAN
#define PLYUNIT_BATCH_EXPORTS
#include <Python.h>

#include "plyunit_batch.h"

#include <stdint.h>
#include <string.h>

static int parse_ptr(PyObject *obj, void **out)
{
    if (obj == NULL || obj == Py_None) {
        *out = NULL;
        return 0;
    }
    if (PyLong_Check(obj)) {
        *out = PyLong_AsVoidPtr(obj);
        return 0;
    }
    PyErr_SetString(PyExc_TypeError, "function pointer must be int address or None");
    return -1;
}

static PyObject *py_set_rlgl(PyObject *self, PyObject *args)
{
    PyObject *dict;
    PlyunitRlglDispatch d;
    PyObject *v;
    void *p;

    (void)self;
    memset(&d, 0, sizeof(d));
    if (!PyArg_ParseTuple(args, "O", &dict)) {
        return NULL;
    }
    if (!PyDict_Check(dict)) {
        PyErr_SetString(PyExc_TypeError, "set_rlgl expects a dict");
        return NULL;
    }

#define GET_FN(key, field, cast) \
    do { \
        v = PyDict_GetItemString(dict, key); \
        if (v == NULL) { \
            PyErr_SetString(PyExc_KeyError, key); \
            return NULL; \
        } \
        if (parse_ptr(v, &p) < 0) return NULL; \
        d.field = (cast)p; \
    } while (0)

#define GET_FN_OPT(key, field, cast) \
    do { \
        v = PyDict_GetItemString(dict, key); \
        if (v != NULL && v != Py_None) { \
            if (parse_ptr(v, &p) < 0) return NULL; \
            d.field = (cast)p; \
        } \
    } while (0)

#define GET_INT(key, field) \
    do { \
        v = PyDict_GetItemString(dict, key); \
        if (v == NULL || !PyLong_Check(v)) { \
            PyErr_SetString(PyExc_TypeError, key " must be int"); \
            return NULL; \
        } \
        d.field = (int)PyLong_AsLong(v); \
    } while (0)

#define GET_UINT(key, field) \
    do { \
        v = PyDict_GetItemString(dict, key); \
        if (v == NULL || !PyLong_Check(v)) { \
            PyErr_SetString(PyExc_TypeError, key " must be int"); \
            return NULL; \
        } \
        d.field = (unsigned int)PyLong_AsUnsignedLong(v); \
    } while (0)

    GET_FN("rl_load_vertex_array", rl_load_vertex_array, unsigned int (*)(void));
    GET_FN("rl_enable_vertex_array", rl_enable_vertex_array, int (*)(unsigned int));
    GET_FN("rl_disable_vertex_array", rl_disable_vertex_array, void (*)(void));
    GET_FN("rl_unload_vertex_array", rl_unload_vertex_array, void (*)(unsigned int));
    GET_FN("rl_load_vertex_buffer", rl_load_vertex_buffer,
           unsigned int (*)(const void *, int, int));
    GET_FN("rl_load_vertex_buffer_element", rl_load_vertex_buffer_element,
           unsigned int (*)(const void *, int, int));
    GET_FN("rl_update_vertex_buffer", rl_update_vertex_buffer,
           void (*)(unsigned int, const void *, int, int));
    GET_FN("rl_unload_vertex_buffer", rl_unload_vertex_buffer, void (*)(unsigned int));
    GET_FN("rl_set_vertex_attribute", rl_set_vertex_attribute,
           void (*)(unsigned int, int, int, int, int, int));
    GET_FN("rl_enable_vertex_attribute", rl_enable_vertex_attribute, void (*)(unsigned int));

    GET_FN("gl_bind_vertex_array", gl_bind_vertex_array, void (*)(unsigned int));
    GET_FN("gl_bind_buffer", gl_bind_buffer, void (*)(unsigned int, unsigned int));
    GET_FN("gl_active_texture", gl_active_texture, void (*)(unsigned int));
    GET_FN("gl_bind_texture", gl_bind_texture, void (*)(unsigned int, unsigned int));
    GET_FN("gl_draw_elements", gl_draw_elements,
           void (*)(unsigned int, int, unsigned int, const void *));
    GET_FN_OPT("gl_uniform1i", gl_uniform1i, void (*)(int, int));

    GET_INT("rl_float", rl_float);
    GET_INT("rl_unsigned_byte", rl_unsigned_byte);
    GET_INT("sampler_uniform_loc", sampler_uniform_loc);
    GET_UINT("gl_texture0", gl_texture0);
    GET_UINT("gl_texture_2d", gl_texture_2d);
    GET_UINT("gl_element_array_buffer", gl_element_array_buffer);
    GET_UINT("gl_triangles", gl_triangles);
    GET_UINT("gl_unsigned_int", gl_unsigned_int);

#undef GET_FN
#undef GET_FN_OPT
#undef GET_INT
#undef GET_UINT

    plyunit_ubr_set_rlgl(&d);
    Py_RETURN_NONE;
}

static PyObject *py_clear_rlgl(PyObject *self, PyObject *args)
{
    (void)self;
    (void)args;
    plyunit_ubr_clear_rlgl();
    Py_RETURN_NONE;
}

static PyObject *py_has_rlgl(PyObject *self, PyObject *args)
{
    (void)self;
    (void)args;
    return PyLong_FromLong(plyunit_ubr_has_rlgl());
}

static PyObject *py_ubr_init(PyObject *self, PyObject *args)
{
    int max_sprites;
    int code;
    (void)self;
    if (!PyArg_ParseTuple(args, "i", &max_sprites)) {
        return NULL;
    }
    code = plyunit_ubr_init(max_sprites);
    if (code != PLYUNIT_OK) {
        return PyErr_Format(
            PyExc_RuntimeError,
            "ubr_init failed code=%d (bind set_rlgl first; GL context required)",
            code);
    }
    Py_RETURN_NONE;
}

static PyObject *py_ubr_shutdown(PyObject *self, PyObject *args)
{
    (void)self;
    (void)args;
    plyunit_ubr_shutdown();
    Py_RETURN_NONE;
}

static PyObject *py_ubr_is_ready(PyObject *self, PyObject *args)
{
    (void)self;
    (void)args;
    return PyLong_FromLong(plyunit_ubr_is_ready());
}

static void release_buf(Py_buffer *b)
{
    if (b->obj != NULL) {
        PyBuffer_Release(b);
        b->obj = NULL;
    }
}

static PyObject *py_ubr_submit_frame(PyObject *self, PyObject *args)
{
    PyObject *o_pos, *o_size, *o_origin, *o_rot, *o_rgba, *o_uv;
    PyObject *o_starts, *o_counts, *o_tex;
    int n_sprites, n_runs;
    Py_buffer b_pos = {0}, b_size = {0}, b_origin = {0}, b_rot = {0};
    Py_buffer b_rgba = {0}, b_uv = {0};
    Py_buffer b_starts = {0}, b_counts = {0}, b_tex = {0};
    int code;
    int ok = 0;

    (void)self;
    if (!PyArg_ParseTuple(
            args,
            "OOOOOOOOOii",
            &o_pos,
            &o_size,
            &o_origin,
            &o_rot,
            &o_rgba,
            &o_uv,
            &o_starts,
            &o_counts,
            &o_tex,
            &n_sprites,
            &n_runs)) {
        return NULL;
    }

    if (n_sprites < 0 || n_runs < 0) {
        PyErr_SetString(PyExc_ValueError, "n_sprites/n_runs must be >= 0");
        return NULL;
    }
    if (n_sprites == 0) {
        return PyLong_FromLong(PLYUNIT_OK);
    }

    if (PyObject_GetBuffer(o_pos, &b_pos, PyBUF_SIMPLE) < 0) goto fail;
    if (PyObject_GetBuffer(o_size, &b_size, PyBUF_SIMPLE) < 0) goto fail;
    if (PyObject_GetBuffer(o_origin, &b_origin, PyBUF_SIMPLE) < 0) goto fail;
    if (PyObject_GetBuffer(o_rot, &b_rot, PyBUF_SIMPLE) < 0) goto fail;
    if (PyObject_GetBuffer(o_rgba, &b_rgba, PyBUF_SIMPLE) < 0) goto fail;
    if (PyObject_GetBuffer(o_uv, &b_uv, PyBUF_SIMPLE) < 0) goto fail;
    if (n_runs > 0) {
        if (PyObject_GetBuffer(o_starts, &b_starts, PyBUF_SIMPLE) < 0) goto fail;
        if (PyObject_GetBuffer(o_counts, &b_counts, PyBUF_SIMPLE) < 0) goto fail;
        if (PyObject_GetBuffer(o_tex, &b_tex, PyBUF_SIMPLE) < 0) goto fail;
    }

    if (b_pos.len < (Py_ssize_t)n_sprites * 2 * (Py_ssize_t)sizeof(float) ||
        b_size.len < (Py_ssize_t)n_sprites * 2 * (Py_ssize_t)sizeof(float) ||
        b_origin.len < (Py_ssize_t)n_sprites * 2 * (Py_ssize_t)sizeof(float) ||
        b_rot.len < (Py_ssize_t)n_sprites * (Py_ssize_t)sizeof(float) ||
        b_rgba.len < (Py_ssize_t)n_sprites * 4 ||
        b_uv.len < (Py_ssize_t)n_sprites * 4 * (Py_ssize_t)sizeof(float)) {
        PyErr_SetString(PyExc_ValueError, "SoA buffer too small for n_sprites");
        goto fail;
    }
    if (n_runs > 0) {
        if (b_starts.len < (Py_ssize_t)n_runs * (Py_ssize_t)sizeof(int32_t) ||
            b_counts.len < (Py_ssize_t)n_runs * (Py_ssize_t)sizeof(int32_t) ||
            b_tex.len < (Py_ssize_t)n_runs * (Py_ssize_t)sizeof(uint32_t)) {
            PyErr_SetString(PyExc_ValueError, "run buffers too small for n_runs");
            goto fail;
        }
    }

    code = plyunit_ubr_submit_frame(
        (const float *)b_pos.buf,
        (const float *)b_size.buf,
        (const float *)b_origin.buf,
        (const float *)b_rot.buf,
        (const uint8_t *)b_rgba.buf,
        (const float *)b_uv.buf,
        n_runs > 0 ? (const int32_t *)b_starts.buf : NULL,
        n_runs > 0 ? (const int32_t *)b_counts.buf : NULL,
        n_runs > 0 ? (const uint32_t *)b_tex.buf : NULL,
        n_sprites,
        n_runs);

    if (code != PLYUNIT_OK) {
        PyErr_Format(PyExc_RuntimeError, "ubr_submit_frame failed code=%d", code);
        goto fail;
    }
    ok = 1;

fail:
    release_buf(&b_pos);
    release_buf(&b_size);
    release_buf(&b_origin);
    release_buf(&b_rot);
    release_buf(&b_rgba);
    release_buf(&b_uv);
    release_buf(&b_starts);
    release_buf(&b_counts);
    release_buf(&b_tex);
    if (!ok) {
        return NULL;
    }
    return PyLong_FromLong(PLYUNIT_OK);
}

static PyObject *py_version(PyObject *self, PyObject *args)
{
    (void)self;
    (void)args;
    return PyUnicode_FromString(plyunit_batch_version());
}

static PyMethodDef methods[] = {
    {"set_rlgl", py_set_rlgl, METH_VARARGS, "Bind rlgl + GL function pointers"},
    {"clear_rlgl", py_clear_rlgl, METH_NOARGS, "Clear dispatch"},
    {"has_rlgl", py_has_rlgl, METH_NOARGS, "1 if dispatch complete"},
    {"ubr_init", py_ubr_init, METH_VARARGS, "Init VAO/VBO/EBO"},
    {"ubr_shutdown", py_ubr_shutdown, METH_NOARGS, "Release resources"},
    {"ubr_is_ready", py_ubr_is_ready, METH_NOARGS, "1 after successful ubr_init"},
    {"ubr_submit_frame", py_ubr_submit_frame, METH_VARARGS,
     "Expand SoA, upload, glDrawElements runs"},
    {"version", py_version, METH_NOARGS, "Extension version string"},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "plyunit._plyunit_batch",
    "plyunit UBR C extension",
    -1,
    methods,
};

PyMODINIT_FUNC PyInit__plyunit_batch(void)
{
    return PyModule_Create(&moduledef);
}

#ifndef PLYUNIT_BATCH_H
#define PLYUNIT_BATCH_H

#include <stdint.h>

#ifdef _WIN32
  #ifdef PLYUNIT_BATCH_EXPORTS
    #define PLYUNIT_API __declspec(dllexport)
  #else
    #define PLYUNIT_API __declspec(dllexport)
  #endif
#else
  #define PLYUNIT_API __attribute__((visibility("default")))
#endif

#define PLYUNIT_OK                 0
#define PLYUNIT_ERR_INVALID_ARG   -1
#define PLYUNIT_ERR_NO_DISPATCH   -2
#define PLYUNIT_ERR_BAD_BUFFER    -3
#define PLYUNIT_ERR_NOT_INIT      -4
#define PLYUNIT_ERR_CAPACITY      -5

/*
 * Buffer setup uses rlgl. Draw uses raw GL (glDrawElements) because
 * rlDrawVertexArrayElements is a no-op for custom VAOs on current raylib
 * builds — verified: prepare+glDrawElements works, full rl path draws 0 px.
 *
 * Shader/MVP must be prepared by the Python adapter before submit.
 */
typedef struct PlyunitRlglDispatch {
    unsigned int (*rl_load_vertex_array)(void);
    int (*rl_enable_vertex_array)(unsigned int vaoId); /* raylib returns bool */
    void (*rl_disable_vertex_array)(void);
    void (*rl_unload_vertex_array)(unsigned int vaoId);

    unsigned int (*rl_load_vertex_buffer)(const void *buffer, int size, int dynamic);
    unsigned int (*rl_load_vertex_buffer_element)(const void *buffer, int size, int dynamic);
    void (*rl_update_vertex_buffer)(unsigned int bufferId, const void *data, int dataSize, int offset);
    void (*rl_unload_vertex_buffer)(unsigned int vboId);

    void (*rl_set_vertex_attribute)(
        unsigned int index, int componentCount, int type,
        int normalized, int stride, int offset);
    void (*rl_enable_vertex_attribute)(unsigned int index);

    /* Raw GL (from rlGetProcAddress) */
    void (*gl_bind_vertex_array)(unsigned int array);
    void (*gl_bind_buffer)(unsigned int target, unsigned int buffer);
    void (*gl_active_texture)(unsigned int texture);
    void (*gl_bind_texture)(unsigned int target, unsigned int texture);
    void (*gl_draw_elements)(unsigned int mode, int count, unsigned int type, const void *indices);
    void (*gl_uniform1i)(int location, int v0);

    int rl_float;
    int rl_unsigned_byte;
    int sampler_uniform_loc; /* glGetUniformLocation texture0, or -1 */
    unsigned int gl_texture0;
    unsigned int gl_texture_2d;
    unsigned int gl_element_array_buffer;
    unsigned int gl_triangles;
    unsigned int gl_unsigned_int;
} PlyunitRlglDispatch;

PLYUNIT_API void plyunit_ubr_set_rlgl(const PlyunitRlglDispatch *dispatch);
PLYUNIT_API void plyunit_ubr_clear_rlgl(void);
PLYUNIT_API int  plyunit_ubr_has_rlgl(void);

PLYUNIT_API int  plyunit_ubr_init(int max_sprites);
PLYUNIT_API void plyunit_ubr_shutdown(void);
PLYUNIT_API int  plyunit_ubr_is_ready(void);

PLYUNIT_API int plyunit_ubr_submit_frame(
    const float *pos_xy,
    const float *size_wh,
    const float *origin_xy,
    const float *rotation_deg,
    const uint8_t *rgba,
    const float *uv_rect,
    const int32_t *run_starts,
    const int32_t *run_counts,
    const uint32_t *run_tex_ids,
    int n_sprites,
    int n_runs);

PLYUNIT_API const char *plyunit_batch_version(void);

#endif

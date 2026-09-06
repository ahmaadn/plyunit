#include "plyunit_batch.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* Default shader attribute locations (raylib / rlgl). */
#define LOC_POSITION 0
#define LOC_TEXCOORD 1
#define LOC_COLOR    3

static PlyunitRlglDispatch g_rlgl;
static int g_has_rlgl = 0;

static int g_ready = 0;
static int g_max_sprites = 0;
static unsigned int g_vao = 0;
static unsigned int g_vbo_pos = 0;
static unsigned int g_vbo_uv = 0;
static unsigned int g_vbo_col = 0;
static unsigned int g_ebo = 0;

/* CPU staging after expand (owned by native, sized at init). */
static float *g_verts_xyz = NULL;   /* n*4 * 3 */
static float *g_uvs = NULL;         /* n*4 * 2 */
static uint8_t *g_colors = NULL;    /* n*4 * 4 */
static uint32_t *g_ebo_cpu = NULL;  /* n*6 */

void plyunit_ubr_set_rlgl(const PlyunitRlglDispatch *dispatch)
{
    if (dispatch == NULL) {
        memset(&g_rlgl, 0, sizeof(g_rlgl));
        g_has_rlgl = 0;
        return;
    }
    g_rlgl = *dispatch;
    g_has_rlgl =
        g_rlgl.rl_load_vertex_array != NULL &&
        g_rlgl.rl_enable_vertex_array != NULL &&
        g_rlgl.rl_disable_vertex_array != NULL &&
        g_rlgl.rl_unload_vertex_array != NULL &&
        g_rlgl.rl_load_vertex_buffer != NULL &&
        g_rlgl.rl_load_vertex_buffer_element != NULL &&
        g_rlgl.rl_update_vertex_buffer != NULL &&
        g_rlgl.rl_unload_vertex_buffer != NULL &&
        g_rlgl.rl_set_vertex_attribute != NULL &&
        g_rlgl.rl_enable_vertex_attribute != NULL &&
        g_rlgl.gl_bind_vertex_array != NULL &&
        g_rlgl.gl_bind_buffer != NULL &&
        g_rlgl.gl_active_texture != NULL &&
        g_rlgl.gl_bind_texture != NULL &&
        g_rlgl.gl_draw_elements != NULL;
}

void plyunit_ubr_clear_rlgl(void)
{
    memset(&g_rlgl, 0, sizeof(g_rlgl));
    g_has_rlgl = 0;
}

int plyunit_ubr_has_rlgl(void)
{
    return g_has_rlgl ? 1 : 0;
}

int plyunit_ubr_is_ready(void)
{
    return g_ready ? 1 : 0;
}

const char *plyunit_batch_version(void)
{
    return "0.2.3-ubr";
}

static void free_cpu(void)
{
    free(g_verts_xyz);
    free(g_uvs);
    free(g_colors);
    free(g_ebo_cpu);
    g_verts_xyz = NULL;
    g_uvs = NULL;
    g_colors = NULL;
    g_ebo_cpu = NULL;
}

void plyunit_ubr_shutdown(void)
{
    if (g_ready && g_has_rlgl) {
        if (g_vbo_pos) g_rlgl.rl_unload_vertex_buffer(g_vbo_pos);
        if (g_vbo_uv) g_rlgl.rl_unload_vertex_buffer(g_vbo_uv);
        if (g_vbo_col) g_rlgl.rl_unload_vertex_buffer(g_vbo_col);
        if (g_ebo) g_rlgl.rl_unload_vertex_buffer(g_ebo);
        if (g_vao) g_rlgl.rl_unload_vertex_array(g_vao);
    }
    g_vao = g_vbo_pos = g_vbo_uv = g_vbo_col = g_ebo = 0;
    free_cpu();
    g_max_sprites = 0;
    g_ready = 0;
}

int plyunit_ubr_init(int max_sprites)
{
    int max_v, max_i, i, q;
    size_t pos_bytes, uv_bytes, col_bytes, ebo_bytes;

    if (max_sprites <= 0) {
        return PLYUNIT_ERR_INVALID_ARG;
    }
    if (!g_has_rlgl) {
        return PLYUNIT_ERR_NO_DISPATCH;
    }
    if (g_ready) {
        plyunit_ubr_shutdown();
    }

    g_max_sprites = max_sprites;
    max_v = max_sprites * 4;
    max_i = max_sprites * 6;

    g_verts_xyz = (float *)malloc((size_t)max_v * 3 * sizeof(float));
    g_uvs = (float *)malloc((size_t)max_v * 2 * sizeof(float));
    g_colors = (uint8_t *)malloc((size_t)max_v * 4 * sizeof(uint8_t));
    g_ebo_cpu = (uint32_t *)malloc((size_t)max_i * sizeof(uint32_t));
    if (!g_verts_xyz || !g_uvs || !g_colors || !g_ebo_cpu) {
        free_cpu();
        return PLYUNIT_ERR_BAD_BUFFER;
    }

    /* Static EBO: (0,1,2, 0,2,3) per quad */
    for (i = 0; i < max_sprites; i++) {
        q = i * 6;
        g_ebo_cpu[q + 0] = (uint32_t)(i * 4 + 0);
        g_ebo_cpu[q + 1] = (uint32_t)(i * 4 + 1);
        g_ebo_cpu[q + 2] = (uint32_t)(i * 4 + 2);
        g_ebo_cpu[q + 3] = (uint32_t)(i * 4 + 0);
        g_ebo_cpu[q + 4] = (uint32_t)(i * 4 + 2);
        g_ebo_cpu[q + 5] = (uint32_t)(i * 4 + 3);
    }

    memset(g_verts_xyz, 0, (size_t)max_v * 3 * sizeof(float));
    memset(g_uvs, 0, (size_t)max_v * 2 * sizeof(float));
    memset(g_colors, 0, (size_t)max_v * 4 * sizeof(uint8_t));

    pos_bytes = (size_t)max_v * 3 * sizeof(float);
    uv_bytes = (size_t)max_v * 2 * sizeof(float);
    col_bytes = (size_t)max_v * 4 * sizeof(uint8_t);
    ebo_bytes = (size_t)max_i * sizeof(uint32_t);

    g_vao = g_rlgl.rl_load_vertex_array();
    g_rlgl.rl_enable_vertex_array(g_vao);

    g_vbo_pos = g_rlgl.rl_load_vertex_buffer(g_verts_xyz, (int)pos_bytes, 1);
    g_rlgl.rl_set_vertex_attribute(
        LOC_POSITION, 3, g_rlgl.rl_float, 0, 0, 0);
    g_rlgl.rl_enable_vertex_attribute(LOC_POSITION);

    g_vbo_uv = g_rlgl.rl_load_vertex_buffer(g_uvs, (int)uv_bytes, 1);
    g_rlgl.rl_set_vertex_attribute(
        LOC_TEXCOORD, 2, g_rlgl.rl_float, 0, 0, 0);
    g_rlgl.rl_enable_vertex_attribute(LOC_TEXCOORD);

    g_vbo_col = g_rlgl.rl_load_vertex_buffer(g_colors, (int)col_bytes, 1);
    g_rlgl.rl_set_vertex_attribute(
        LOC_COLOR, 4, g_rlgl.rl_unsigned_byte, 1, 0, 0);
    g_rlgl.rl_enable_vertex_attribute(LOC_COLOR);

    g_ebo = g_rlgl.rl_load_vertex_buffer_element(
        g_ebo_cpu, (int)ebo_bytes, 0);

    g_rlgl.rl_disable_vertex_array();
    g_ready = 1;
    return PLYUNIT_OK;
}

static void expand_sprite(
    int i,
    const float *pos_xy,
    const float *size_wh,
    const float *origin_xy,
    const float *rotation_deg,
    const uint8_t *rgba,
    const float *uv_rect)
{
    float px = pos_xy[i * 2 + 0];
    float py = pos_xy[i * 2 + 1];
    float dw = size_wh[i * 2 + 0];
    float dh = size_wh[i * 2 + 1];
    float ox = origin_xy[i * 2 + 0];
    float oy = origin_xy[i * 2 + 1];
    float rot = rotation_deg[i];
    float u0 = uv_rect[i * 4 + 0];
    float v0 = uv_rect[i * 4 + 1];
    float u1 = uv_rect[i * 4 + 2];
    float v1 = uv_rect[i * 4 + 3];
    unsigned char r = rgba[i * 4 + 0];
    unsigned char g = rgba[i * 4 + 1];
    unsigned char b = rgba[i * 4 + 2];
    unsigned char a = rgba[i * 4 + 3];

    int base = i * 4;
    float corners_x[4];
    float corners_y[4];
    float us[4] = {u0, u0, u1, u1};
    float vs[4] = {v0, v1, v1, v0};
    int c;

    if (rot == 0.0f) {
        float x0 = px - ox;
        float y0 = py - oy;
        corners_x[0] = x0;
        corners_y[0] = y0;
        corners_x[1] = x0;
        corners_y[1] = y0 + dh;
        corners_x[2] = x0 + dw;
        corners_y[2] = y0 + dh;
        corners_x[3] = x0 + dw;
        corners_y[3] = y0;
    } else {
        float rad = rot * (float)(M_PI / 180.0);
        float cos_r = cosf(rad);
        float sin_r = sinf(rad);
        float lx[4] = {-ox, -ox, -ox + dw, -ox + dw};
        float ly[4] = {-oy, -oy + dh, -oy + dh, -oy};
        for (c = 0; c < 4; c++) {
            corners_x[c] = lx[c] * cos_r - ly[c] * sin_r + px;
            corners_y[c] = lx[c] * sin_r + ly[c] * cos_r + py;
        }
    }

    for (c = 0; c < 4; c++) {
        int vi = base + c;
        g_verts_xyz[vi * 3 + 0] = corners_x[c];
        g_verts_xyz[vi * 3 + 1] = corners_y[c];
        g_verts_xyz[vi * 3 + 2] = 0.0f;
        g_uvs[vi * 2 + 0] = us[c];
        g_uvs[vi * 2 + 1] = vs[c];
        g_colors[vi * 4 + 0] = r;
        g_colors[vi * 4 + 1] = g;
        g_colors[vi * 4 + 2] = b;
        g_colors[vi * 4 + 3] = a;
    }
}

int plyunit_ubr_submit_frame(
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
    int n_runs)
{
    int i, r;
    int n_verts;
    int pos_bytes, uv_bytes, col_bytes;

    if (!g_ready) {
        return PLYUNIT_ERR_NOT_INIT;
    }
    if (!g_has_rlgl) {
        return PLYUNIT_ERR_NO_DISPATCH;
    }
    if (n_sprites < 0 || n_runs < 0) {
        return PLYUNIT_ERR_INVALID_ARG;
    }
    if (n_sprites == 0) {
        return PLYUNIT_OK;
    }
    if (n_sprites > g_max_sprites) {
        return PLYUNIT_ERR_CAPACITY;
    }
    if (!pos_xy || !size_wh || !origin_xy || !rotation_deg ||
        !rgba || !uv_rect) {
        return PLYUNIT_ERR_INVALID_ARG;
    }
    if (n_runs > 0 && (!run_starts || !run_counts || !run_tex_ids)) {
        return PLYUNIT_ERR_INVALID_ARG;
    }

    for (i = 0; i < n_sprites; i++) {
        expand_sprite(
            i, pos_xy, size_wh, origin_xy, rotation_deg, rgba, uv_rect);
    }

    n_verts = n_sprites * 4;
    pos_bytes = n_verts * 3 * (int)sizeof(float);
    uv_bytes = n_verts * 2 * (int)sizeof(float);
    col_bytes = n_verts * 4 * (int)sizeof(uint8_t);

    g_rlgl.rl_update_vertex_buffer(g_vbo_pos, g_verts_xyz, pos_bytes, 0);
    g_rlgl.rl_update_vertex_buffer(g_vbo_uv, g_uvs, uv_bytes, 0);
    g_rlgl.rl_update_vertex_buffer(g_vbo_col, g_colors, col_bytes, 0);

    /* Shader/MVP prepared by Python. Draw via raw GL (rlDrawVAE is broken
       for custom VAOs on raylib-python-cffi). */
    g_rlgl.gl_bind_vertex_array(g_vao);
    g_rlgl.gl_bind_buffer(g_rlgl.gl_element_array_buffer, g_ebo);
    g_rlgl.gl_active_texture(g_rlgl.gl_texture0);

    for (r = 0; r < n_runs; r++) {
        int start = run_starts[r];
        int count = run_counts[r];
        unsigned int tex = run_tex_ids[r];
        int index_count;
        const void *index_ptr;
        if (count <= 0) {
            continue;
        }
        if (start < 0 || start + count > n_sprites) {
            g_rlgl.gl_bind_vertex_array(0);
            g_rlgl.gl_bind_texture(g_rlgl.gl_texture_2d, 0);
            return PLYUNIT_ERR_INVALID_ARG;
        }
        g_rlgl.gl_bind_texture(g_rlgl.gl_texture_2d, tex);
        if (g_rlgl.gl_uniform1i != NULL && g_rlgl.sampler_uniform_loc >= 0) {
            g_rlgl.gl_uniform1i(g_rlgl.sampler_uniform_loc, 0);
        }
        index_count = count * 6;
        /* byte offset into EBO for first index of this run */
        index_ptr = (const void *)(uintptr_t)((size_t)start * 6u * sizeof(uint32_t));
        g_rlgl.gl_draw_elements(
            g_rlgl.gl_triangles,
            index_count,
            g_rlgl.gl_unsigned_int,
            index_ptr);
    }

    g_rlgl.gl_bind_vertex_array(0);
    g_rlgl.gl_bind_texture(g_rlgl.gl_texture_2d, 0);
    return PLYUNIT_OK;
}

/* Compile-only smoke test for the arm64 NEON constructs injected into k3_ops.c. */
#include <arm_neon.h>
#include <stdint.h>

static double bf16_dot(const uint16_t *row, const float *x, int n)
{
    float64x2_t v01 = vdupq_n_f64(0.0);
    float64x2_t v23 = vdupq_n_f64(0.0);
    int i = 0;
    for (; i + 3 < n; i += 4) {
        const uint16x4_t h = vld1_u16(row + i);
        const uint32x4_t b32 = vshlq_n_u32(vmovl_u16(h), 16);
        const float32x4_t wf = vreinterpretq_f32_u32(b32);
        const float32x4_t xf = vld1q_f32(x + i);
        const float64x2_t w01 = vcvt_f64_f32(vget_low_f32(wf));
        const float64x2_t w23 = vcvt_f64_f32(vget_high_f32(wf));
        const float64x2_t x01 = vcvt_f64_f32(vget_low_f32(xf));
        const float64x2_t x23 = vcvt_f64_f32(vget_high_f32(xf));
        v01 = vaddq_f64(v01, vmulq_f64(w01, x01));
        v23 = vaddq_f64(v23, vmulq_f64(w23, x23));
    }
    double acc = (vgetq_lane_f64(v01, 0) + vgetq_lane_f64(v01, 1)) +
                 (vgetq_lane_f64(v23, 0) + vgetq_lane_f64(v23, 1));
    for (; i < n; i++) {
        union { uint32_t u; float f; } w = {(uint32_t)row[i] << 16};
        acc += (double)w.f * (double)x[i];
    }
    return acc;
}

static double f32_dot(const float *w, const float *x, int n)
{
    float64x2_t v01 = vdupq_n_f64(0.0);
    float64x2_t v23 = vdupq_n_f64(0.0);
    int i = 0;
    for (; i + 3 < n; i += 4) {
        const float32x4_t wf4 = vld1q_f32(w + i);
        const float32x4_t xf4 = vld1q_f32(x + i);
        const float64x2_t w01 = vcvt_f64_f32(vget_low_f32(wf4));
        const float64x2_t w23 = vcvt_f64_f32(vget_high_f32(wf4));
        const float64x2_t x01 = vcvt_f64_f32(vget_low_f32(xf4));
        const float64x2_t x23 = vcvt_f64_f32(vget_high_f32(xf4));
        v01 = vaddq_f64(v01, vmulq_f64(w01, x01));
        v23 = vaddq_f64(v23, vmulq_f64(w23, x23));
    }
    double acc = (vgetq_lane_f64(v01, 0) + vgetq_lane_f64(v01, 1)) +
                 (vgetq_lane_f64(v23, 0) + vgetq_lane_f64(v23, 1));
    for (; i < n; i++) acc += (double)w[i] * (double)x[i];
    return acc;
}

int neon_smoke(const uint16_t *b, const float *w, const float *x, int n)
{
    return (int)(bf16_dot(b, x, n) + f32_dot(w, x, n));
}

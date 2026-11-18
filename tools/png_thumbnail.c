/* Streaming area-average PNG reduction. Memory is O(width), not O(width*height).
 * Compile: cc -O2 png_thumbnail.c -lpng -o png_thumbnail
 * Usage: png_thumbnail input.png output.ppm factor
 * Alpha is composited onto white before averaging; no nearest-neighbor aliasing.
 */
#include <png.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    if (argc != 4) return 2;
    int factor = atoi(argv[3]);
    if (factor < 1 || factor > 64) return 2;
    FILE *in = fopen(argv[1], "rb");
    FILE *out = fopen(argv[2], "wb");
    if (!in || !out) return 3;
    png_structp png = png_create_read_struct(PNG_LIBPNG_VER_STRING, NULL, NULL, NULL);
    png_infop info = png_create_info_struct(png);
    if (!png || !info || setjmp(png_jmpbuf(png))) return 4;
    png_init_io(png, in);
    png_read_info(png, info);
    unsigned w = png_get_image_width(png, info), h = png_get_image_height(png, info);
    int type = png_get_color_type(png, info), depth = png_get_bit_depth(png, info);
    if ((uint64_t)w*h > 160000000 || png_get_interlace_type(png, info) != PNG_INTERLACE_NONE) return 5;
    if (depth == 16) png_set_strip_16(png);
    if (type == PNG_COLOR_TYPE_PALETTE) png_set_palette_to_rgb(png);
    if (type == PNG_COLOR_TYPE_GRAY && depth < 8) png_set_expand_gray_1_2_4_to_8(png);
    int transparency = png_get_valid(png, info, PNG_INFO_tRNS);
    if (transparency) png_set_tRNS_to_alpha(png);
    if (type == PNG_COLOR_TYPE_GRAY || type == PNG_COLOR_TYPE_GRAY_ALPHA) png_set_gray_to_rgb(png);
    if (!(type & PNG_COLOR_MASK_ALPHA) && !transparency) png_set_filler(png, 255, PNG_FILLER_AFTER);
    png_read_update_info(png, info);
    if (png_get_channels(png, info) != 4) return 6;
    unsigned tw = (w+factor-1)/factor, th = (h+factor-1)/factor;
    png_bytep row = malloc(png_get_rowbytes(png, info));
    uint32_t *sum = calloc((size_t)tw*3, sizeof(uint32_t));
    unsigned char *reduced = malloc((size_t)tw*3);
    if (!row || !sum || !reduced) return 7;
    fprintf(out, "P6\n%u %u\n255\n", tw, th);
    unsigned rows = 0;
    for (unsigned y=0; y<h; y++) {
        png_read_row(png, row, NULL);
        for (unsigned x=0; x<w; x++) {
            unsigned alpha = row[x*4+3], tx = x/factor;
            for (unsigned c=0; c<3; c++)
                sum[tx*3+c] += (row[x*4+c]*alpha + 255*(255-alpha) + 127)/255;
        }
        rows++;
        if (rows == (unsigned)factor || y+1 == h) {
            for (unsigned x=0; x<tw; x++) {
                unsigned cols = w-x*factor < (unsigned)factor ? w-x*factor : (unsigned)factor;
                unsigned n = rows*cols;
                for (unsigned c=0; c<3; c++) reduced[x*3+c] = (sum[x*3+c]+n/2)/n;
            }
            if (fwrite(reduced, 3, tw, out) != tw) return 8;
            memset(sum, 0, (size_t)tw*3*sizeof(uint32_t));
            rows = 0;
        }
    }
    png_read_end(png, NULL);
    png_destroy_read_struct(&png, &info, NULL);
    free(row); free(sum); free(reduced);
    fclose(in); fclose(out);
    return 0;
}

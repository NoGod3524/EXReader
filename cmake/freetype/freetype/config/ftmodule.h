/* SPDX-License-Identifier: MIT */
/*
 * FreeType module table for EXReader, used instead of the upstream
 * include/freetype/config/ftmodule.h (cmake/deps.cmake puts this directory
 * first on the freetype target's include path).
 *
 * EXReader loads scalable SFNT/CFF/Type 1/CID faces and color-bitmap SFNT
 * faces, and renders with FT_RENDER_MODE_NORMAL. It does not register the
 * BDF, PCF, Windows FNT, PFR, Type 42 and HVF drivers, the 1-bit raster, SDF
 * and OT-SVG renderers: unreferenced, they are not linked. gzip stays because
 * the sfnt driver uses it to read WOFF fonts.
 */
FT_USE_MODULE( FT_Module_Class, autofit_module_class )
FT_USE_MODULE( FT_Driver_ClassRec, tt_driver_class )
FT_USE_MODULE( FT_Driver_ClassRec, t1_driver_class )
FT_USE_MODULE( FT_Driver_ClassRec, cff_driver_class )
FT_USE_MODULE( FT_Driver_ClassRec, t1cid_driver_class )
FT_USE_MODULE( FT_Module_Class, psaux_module_class )
FT_USE_MODULE( FT_Module_Class, psnames_module_class )
FT_USE_MODULE( FT_Module_Class, pshinter_module_class )
FT_USE_MODULE( FT_Module_Class, sfnt_module_class )
FT_USE_MODULE( FT_Renderer_Class, ft_smooth_renderer_class )

/* EOF */

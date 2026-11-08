/* SPDX-License-Identifier: MIT */
/* Deterministic content navigation and live font replacement for --drive. */
  if(!strcmp(action,"annotgoto")) {
    size_t part=(size_t)strtoull(drive_args[1],NULL,10),offset=(size_t)strtoull(drive_args[2],NULL,10);
    exr_document *doc=NULL;host_job *job=job_new(JOB_GO);
    if(!job || exr_publication_load(select_publication(),part,&doc,NULL)!=EXR_OK ||
       exr_anchor_create(doc,offset,offset,&job->anchor,NULL)!=EXR_OK) {
      if(job)job_release(job);
      exr_document_free(doc);drive_step_finish(0,"content navigation failed");return 0;
    }
    exr_document_free(doc);job->book_id=g.frame.book_id;job->use_offset=job->has_anchor=job->shell_search_jump=1;
    job->target_part=part;job->target_offset=offset;
    if(g.session.bounded) {
      size_t n;const exr_part *parts=exr_publication_parts(g.session.publication,&n);
      if(part>=n || !(job->part_path=host_strdup(parts[part].path))){job_release(job);drive_step_finish(0,"part unavailable");return 0;}
    }
    job_submit(job);drive_expect_idle=1;return 1;
  }
  if (!strcmp(action,"annotfont")) {
    exr_font *font=NULL;
    if(exr_font_open(drive_args[1],&font,NULL)!=EXR_OK){drive_step_finish(0,"font open failed");return 0;}
    exr_font_free(g.font);g.font=font;page_cache_clear();
    host_job *job=job_new(JOB_LAYOUT);
    if(!job){drive_step_finish(0,"font job allocation failed");return 0;}
    job->book_id=g.frame.book_id;job->font_percent=g.font_percent;
    job->has_anchor=host_anchor_copy(&job->anchor,&g.frame.point);
    job_submit(job);drive_expect_idle=1;return 1;
  }

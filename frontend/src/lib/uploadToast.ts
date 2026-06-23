type UploadResult = {

  total_rows?: number

  imported: number

  missing?: number

  duplicates_skipped?: number

  already_exists?: number

  parse_warnings?: string[]

}



export function getUploadToastMessage(

  data: UploadResult,

  t: (key: string, vars?: Record<string, string | number>) => string,

): { message: string; type: "success" | "info" | "warning" } {

  const skipped = data.already_exists ?? data.duplicates_skipped ?? 0

  const missing = data.missing ?? 0

  const imported = data.imported

  const total = data.total_rows ?? imported + skipped + missing



  if (total === 0) {

    return { message: t("products.uploadFailed"), type: "warning" }

  }

  if (imported === 0 && (skipped > 0 || missing > 0)) {

    return {

      message: t("products.uploadNoneImported", { total, missing, duplicates: skipped }),

      type: "warning",

    }

  }

  if (skipped === 0 && missing === 0 && imported > 0) {

    return { message: t("products.uploadAllNew", { total, imported }), type: "success" }

  }

  return {

    message: t("products.uploadSummary", { total, imported, missing, duplicates: skipped }),

    type: imported > 0 ? "success" : "warning",

  }

}


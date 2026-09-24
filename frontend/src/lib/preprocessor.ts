import exifr from "exifr";
import JSZip from "jszip";

export interface PreprocessProgress {
  phase: "preparing" | "processing" | "packaging" | "uploading";
  current: number;
  total: number;
  message: string;
}

export interface ClientMediaMetadata {
  id: string;
  hash: string;
  kind: "photo" | "video";
  filename: string;
  normalized_filename: string;
  captured_at: string | null;
  timezone: string;
  time_source: "exif" | "filename" | "mtime";
  lat: number | null;
  lon: number | null;
  location_source: "exif" | "none";
  width: number | null;
  height: number | null;
  orientation: number | null;
  device_id: string | null;
  size_bytes: number;
  thumb_ref: string;
  web_ref: string;
}

export interface PreprocessOptions {
  title: string;
  description?: string | null;
  dateFrom?: string | null;
  dateTo?: string | null;
  enrich?: boolean;
  timelineFile?: File | null;
  gpxFiles?: File[];
  mediaFiles: File[];
  onProgress?: (p: PreprocessProgress) => void;
}

/** Content-addressed quick hash matching backend implementation: sha1(size + first 64KB) */
export async function computeQuickHash(file: File): Promise<string> {
  const slice = await file.slice(0, 65536).arrayBuffer();
  const sizeBytes = new TextEncoder().encode(file.size.toString());
  const combined = new Uint8Array(sizeBytes.byteLength + slice.byteLength);
  combined.set(sizeBytes, 0);
  combined.set(new Uint8Array(slice), sizeBytes.byteLength);
  const hashBuffer = await crypto.subtle.digest("SHA-1", combined);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hex = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
  return hex.slice(0, 20);
}

/** Guess timestamp from common camera filename patterns */
function timeFromFilename(name: string): string | null {
  const pxl = /PXL_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/;
  const img = /IMG_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/;
  const general = /(\d{4})[-_]?(\d{2})[-_]?(\d{2})[-_ T](\d{2})[-_:]?(\d{2})[-_:]?(\d{2})/;

  for (const pat of [pxl, img, general]) {
    const m = pat.exec(name);
    if (m) {
      const [, y, mo, d, hh, mm, ss] = m;
      return `${y}-${mo}-${d}T${hh}:${mm}:${ss}`;
    }
  }
  return null;
}

/** Generate a resized WebP derivative from an image file */
async function generateDerivative(
  bmp: ImageBitmap,
  maxDim: number,
  quality: number
): Promise<Blob> {
  let { width, height } = bmp;
  if (width > maxDim || height > maxDim) {
    if (width > height) {
      height = Math.round((height * maxDim) / width);
      width = maxDim;
    } else {
      width = Math.round((width * maxDim) / height);
      height = maxDim;
    }
  }

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Could not get canvas context");
  ctx.drawImage(bmp, 0, 0, width, height);

  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) resolve(blob);
        else reject(new Error("Failed to encode WebP image"));
      },
      "image/webp",
      quality
    );
  });
}

/** Process all media, package light zip, and upload to the server */
export async function preprocessAndUpload(
  options: PreprocessOptions
): Promise<{ jobId: string; capsuleId: string }> {
  const {
    title,
    description,
    dateFrom,
    dateTo,
    enrich = true,
    timelineFile,
    gpxFiles = [],
    mediaFiles,
    onProgress,
  } = options;

  const zip = new JSZip();
  const metadataList: ClientMediaMetadata[] = [];
  const total = mediaFiles.length;

  onProgress?.({
    phase: "preparing",
    current: 0,
    total,
    message: "Scanning files...",
  });

  // Filter supported image files
  const supported = mediaFiles.filter((f) =>
    /\.(jpe?g|png|webp|heic|heif|tiff?)$/i.test(f.name)
  );

  let processedCount = 0;
  // Concurrency limit for browser image decoding/resizing
  const CONCURRENCY = 4;

  for (let i = 0; i < supported.length; i += CONCURRENCY) {
    const chunk = supported.slice(i, i + CONCURRENCY);
    await Promise.all(
      chunk.map(async (file) => {
        try {
          const hash = await computeQuickHash(file);
          let capturedAt: string | null = null;
          let timeSource: "exif" | "filename" | "mtime" = "mtime";
          let lat: number | null = null;
          let lon: number | null = null;
          let locationSource: "exif" | "none" = "none";
          let width: number | null = null;
          let height: number | null = null;
          let orientation: number | null = null;
          let deviceId: string | null = null;

          // 1. Extract EXIF
          try {
            const exif = await exifr.parse(file, {
              pick: [
                "DateTimeOriginal",
                "CreateDate",
                "ModifyDate",
                "OffsetTimeOriginal",
                "OffsetTime",
                "latitude",
                "longitude",
                "Make",
                "Model",
                "ExifImageWidth",
                "ExifImageHeight",
                "Orientation",
              ],
            });

            if (exif) {
              const dateVal = exif.DateTimeOriginal ?? exif.CreateDate ?? exif.ModifyDate;
              if (dateVal instanceof Date && !isNaN(dateVal.getTime())) {
                capturedAt = dateVal.toISOString();
                timeSource = "exif";
              }
              if (typeof exif.latitude === "number" && typeof exif.longitude === "number") {
                lat = exif.latitude;
                lon = exif.longitude;
                locationSource = "exif";
              }
              if (exif.Make || exif.Model) {
                deviceId = `${exif.Make ?? ""} ${exif.Model ?? ""}`.trim();
              }
              if (typeof exif.Orientation === "number") {
                orientation = exif.Orientation;
              }
            }
          } catch {
            // EXIF parsing failed, proceed with fallbacks
          }

          // Fallback timestamp from filename
          if (!capturedAt) {
            const fromName = timeFromFilename(file.name);
            if (fromName) {
              capturedAt = new Date(fromName).toISOString();
              timeSource = "filename";
            } else if (file.lastModified) {
              capturedAt = new Date(file.lastModified).toISOString();
              timeSource = "mtime";
            }
          }

          // 2. Decode Image & Generate Derivatives
          let bmp: ImageBitmap | null = null;
          try {
            bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
            width = bmp.width;
            height = bmp.height;

            const [thumbBlob, webBlob] = await Promise.all([
              generateDerivative(bmp, 256, 0.78),
              generateDerivative(bmp, 1600, 0.82),
            ]);

            zip.file(`media/thumb/${hash}.webp`, thumbBlob);
            zip.file(`media/web/${hash}.webp`, webBlob);
          } catch {
            // If bitmap decoding fails (e.g. raw or unsupported format), continue
          } finally {
            bmp?.close();
          }

          metadataList.push({
            id: `med_${hash}`,
            hash,
            kind: "photo",
            filename: file.name,
            normalized_filename: file.name,
            captured_at: capturedAt,
            timezone: "UTC",
            time_source: timeSource,
            lat,
            lon,
            location_source: locationSource,
            width,
            height,
            orientation,
            device_id: deviceId,
            size_bytes: file.size,
            thumb_ref: `media/thumb/${hash}.webp`,
            web_ref: `media/web/${hash}.webp`,
          });
        } catch {
          // Ignore individual file error to avoid breaking entire trip
        } finally {
          processedCount++;
          onProgress?.({
            phase: "processing",
            current: processedCount,
            total: supported.length,
            message: `Optimizing photographs: ${processedCount} of ${supported.length}`,
          });
        }
      })
    );
  }

  // 3. Add timeline if present
  if (timelineFile) {
    zip.file("timeline.json", timelineFile);
  }

  // 4. Add GPX tracks if present
  if (gpxFiles.length > 0) {
    for (const gpx of gpxFiles) {
      zip.file(`tracks/${gpx.name}`, gpx);
    }
  }

  // 5. Add metadata JSON
  zip.file("media_metadata.json", JSON.stringify(metadataList, null, 2));

  // 6. Add Ingest Manifest
  zip.file(
    "ingest_manifest.json",
    JSON.stringify(
      {
        title,
        description,
        date_from: dateFrom,
        date_to: dateTo,
        enrich,
      },
      null,
      2
    )
  );

  // 7. Package zip (using STORE for fast non-compressed packing since WebP is already compressed)
  onProgress?.({
    phase: "packaging",
    current: 0,
    total: 1,
    message: "Packaging upload bundle...",
  });

  const zipBlob = await zip.generateAsync(
    { type: "blob", compression: "STORE" },
    (metadata) => {
      onProgress?.({
        phase: "packaging",
        current: Math.round(metadata.percent),
        total: 100,
        message: `Packaging bundle: ${Math.round(metadata.percent)}%`,
      });
    }
  );

  // 8. Upload via XMLHttpRequest to report upload progress
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/capsules/build-preprocessed");

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const mbUploaded = (e.loaded / (1024 * 1024)).toFixed(1);
        const mbTotal = (e.total / (1024 * 1024)).toFixed(1);
        const pct = Math.round((e.loaded / e.total) * 100);
        onProgress?.({
          phase: "uploading",
          current: e.loaded,
          total: e.total,
          message: `Uploading to cloud: ${mbUploaded} MB / ${mbTotal} MB (${pct}%)`,
        });
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const res = JSON.parse(xhr.responseText);
          resolve(res);
        } catch (err) {
          reject(new Error("Invalid JSON response from server"));
        }
      } else {
        try {
          const res = JSON.parse(xhr.responseText);
          reject(new Error(res.detail || `Upload failed with status ${xhr.status}`));
        } catch {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      }
    };

    xhr.onerror = () => reject(new Error("Network error during upload"));

    const formData = new FormData();
    formData.append("file", zipBlob, `${title || "trip"}.zip`);
    xhr.send(formData);
  });
}

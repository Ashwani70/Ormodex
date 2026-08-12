import { useState, useEffect } from "react";
import api, { BACKEND_URL } from "@/lib/api";
import { Upload, X, Image as ImageIcon } from "lucide-react";
import { toast } from "sonner";

export default function ImageUploader({ value, onChange }) {
  // value is the storage path (e.g. "gew-erp/products/.../uuid.png")
  const [busy, setBusy] = useState(false);
  const [previewSrc, setPreviewSrc] = useState(null);

  useEffect(() => {
    let revoked = null;
    const load = async () => {
      if (!value) {
        setPreviewSrc(null);
        return;
      }
      // value can be a full http URL (legacy) or a storage path
      if (value.startsWith("http")) {
        setPreviewSrc(value);
        return;
      }
      try {
        const resp = await api.get(`/files/${value}`, { responseType: "blob" });
        const blobUrl = URL.createObjectURL(resp.data);
        revoked = blobUrl;
        setPreviewSrc(blobUrl);
      } catch {
        setPreviewSrc(null);
      }
    };
    load();
    return () => {
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [value]);

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 6 * 1024 * 1024) {
      toast.error("Image must be under 6MB");
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/uploads/product-image", fd);
      onChange(data.path);
      toast.success("Image uploaded");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  };

  return (
    <div className="space-y-2">
      {previewSrc ? (
        <div className="relative inline-flex items-center justify-center border border-zinc-800 bg-zinc-900/60 rounded-md w-48 h-32 p-2">
          <img
            src={previewSrc}
            alt="Uploaded preview"
            className="max-w-full max-h-full object-contain"
          />
          <button
            type="button"
            data-testid="remove-image"
            onClick={() => onChange("")}
            className="absolute top-1 right-1 w-6 h-6 bg-black/80 text-zinc-300 hover:text-red-400 border border-zinc-700 rounded"
          >
            <X className="w-3.5 h-3.5 mx-auto" />
          </button>
        </div>
      ) : (
        <div className="w-48 h-32 border border-dashed border-zinc-700 flex items-center justify-center rounded-md">
          <ImageIcon className="w-6 h-6 text-zinc-700" />
        </div>
      )}
      <label
        data-testid="upload-image"
        className={`inline-flex items-center gap-2 cursor-pointer border ${
          busy ? "border-zinc-700 text-zinc-500" : "border-zinc-700 text-zinc-300 hover:border-yellow-400 hover:text-yellow-400"
        } px-3 py-2 text-xs font-mono uppercase tracking-wider transition-colors`}
      >
        <Upload className="w-3.5 h-3.5" />
        {busy ? "Uploading…" : "Upload image"}
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          className="hidden"
          onChange={onFile}
          disabled={busy}
        />
      </label>
    </div>
  );
}

// Helper: turn a storage path into a fetch-blob hook for table rows
export function useImageBlob(pathOrUrl) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let revoked = null;
    if (!pathOrUrl) {
      setSrc(null);
      return;
    }
    if (pathOrUrl.startsWith("http")) {
      setSrc(pathOrUrl);
      return;
    }
    api
      .get(`/files/${pathOrUrl}`, { responseType: "blob" })
      .then((resp) => {
        const url = URL.createObjectURL(resp.data);
        revoked = url;
        setSrc(url);
      })
      .catch(() => setSrc(null));
    return () => {
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [pathOrUrl]);
  return src;
}

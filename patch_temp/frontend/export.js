export async function exportFile({ urlBase, kind, hotel_id, columns, rows, metadata, type='excel' }) {
  const url = `${urlBase.replace(/\/$/, '')}/export/${type}`;
  const payload = { kind, hotel_id, columns, rows, metadata };
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    const msg = await res.text().catch(()=> '');
    throw new Error(`Export failed (${res.status}): ${msg}`);
  }
  const blob = await res.blob();
  const link = document.createElement('a');
  const fname = `${kind}_${hotel_id}.${type === 'excel' ? 'xlsx' : 'pdf'}`;
  link.href = URL.createObjectURL(blob);
  link.download = fname;
  document.body.appendChild(link);
  link.click();
  link.remove();
}
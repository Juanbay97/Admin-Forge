import qrcode from "qrcode-generator";

/** Dark modules as merged horizontal runs of one SVG path, on a 1-unit grid (the caller adds the quiet zone through the viewBox). */
export function pathFromMatrix(matrix: boolean[][]): string {
  let path = "";
  matrix.forEach((row, y) => {
    let x = 0;
    while (x < row.length) {
      if (!row[x]) {
        x += 1;
        continue;
      }
      let end = x;
      while (end < row.length && row[end]) end += 1;
      path += `M${x} ${y}h${end - x}v1h-${end - x}z`;
      x = end;
    }
  });
  return path;
}

/** Medium error correction; the module matrix comes from `qrcode-generator` (pure maths: no DOM, no style, no data URI). */
export function qrFor(text: string): { size: number; path: string } {
  const code = qrcode(0, "M");
  code.addData(text);
  code.make();
  const size = code.getModuleCount();
  const matrix = Array.from({ length: size }, (_, row) => Array.from({ length: size }, (_, column) => code.isDark(row, column)));
  return { size, path: pathFromMatrix(matrix) };
}

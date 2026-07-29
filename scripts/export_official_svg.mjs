#!/usr/bin/env node
import esbuild from "esbuild";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { JSDOM } from "jsdom";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const skillDir = path.resolve(__dirname, "..");
const packageDir = skillDir;

function usage() {
  console.error("Usage: node export_official_svg.mjs input.excalidraw output.svg");
}

function installDom(prodDir) {
  const dom = new JSDOM("<!doctype html><html><body></body></html>", {
    pretendToBeVisual: true,
    runScripts: "dangerously",
    url: "http://localhost",
  });
  const win = dom.window;

  win.EXCALIDRAW_ASSET_PATH = `${pathToFileURL(prodDir).href}/`;

  class FontFace {
    constructor(family, source, descriptors = {}) {
      this.family = family;
      this.source = source;
      this.descriptors = descriptors;
      this.status = "unloaded";
      this.unicodeRange = descriptors.unicodeRange || "U+0000-10FFFF";
    }

    async load() {
      this.status = "loaded";
      return this;
    }
  }

  win.FontFace = FontFace;
  globalThis.FontFace = FontFace;

  Object.defineProperty(win.document, "fonts", {
    configurable: true,
    value: {
      add() {},
      delete() {},
      clear() {},
      check() {
        return true;
      },
      load() {
        return Promise.resolve([]);
      },
      ready: Promise.resolve(),
    },
  });

  win.HTMLCanvasElement.prototype.getContext = function getContext() {
    return {
      canvas: this,
      filter: "none",
      font: "20px Excalifont",
      fillStyle: "#1e1e1e",
      strokeStyle: "#1e1e1e",
      textAlign: "left",
      textBaseline: "alphabetic",
      measureText(text) {
        const fontSizeMatch = /(\d+(?:\.\d+)?)px/.exec(this.font || "20px");
        const fontSize = fontSizeMatch ? Number(fontSizeMatch[1]) : 20;
        return {
          width: String(text).length * fontSize * 0.58,
          actualBoundingBoxAscent: fontSize * 0.8,
          actualBoundingBoxDescent: fontSize * 0.2,
        };
      },
      save() {},
      restore() {},
      scale() {},
      translate() {},
      rotate() {},
      clearRect() {},
      fillRect() {},
      strokeRect() {},
      beginPath() {},
      closePath() {},
      moveTo() {},
      lineTo() {},
      bezierCurveTo() {},
      quadraticCurveTo() {},
      arc() {},
      ellipse() {},
      rect() {},
      clip() {},
      fill() {},
      stroke() {},
      fillText() {},
      strokeText() {},
      drawImage() {},
      setLineDash() {},
      getLineDash() {
        return [];
      },
      getImageData() {
        return { data: new Uint8ClampedArray(4), width: 1, height: 1 };
      },
      putImageData() {},
    };
  };

  const localFetch = async (url) => {
    const href = url instanceof URL ? url.href : String(url);
    if (href.startsWith("file://")) {
      const filePath = fileURLToPath(href);
      const data = await fs.promises.readFile(filePath);
      return {
        ok: true,
        statusText: "OK",
        async arrayBuffer() {
          return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
        },
      };
    }
    if (typeof globalThis.fetch === "function") {
      return globalThis.fetch(url);
    }
    throw new Error(`No fetch implementation for ${href}`);
  };

  win.fetch = localFetch;
  globalThis.fetch = localFetch;
  globalThis.window = win;
  globalThis.document = win.document;
  Object.defineProperty(globalThis, "navigator", { value: win.navigator, configurable: true });

  for (const key of [
    "DOMParser",
    "XMLSerializer",
    "HTMLElement",
    "SVGElement",
    "File",
    "Blob",
    "Node",
    "Element",
    "HTMLCanvasElement",
    "Image",
    "CustomEvent",
  ]) {
    if (win[key]) {
      globalThis[key] = win[key];
    }
  }

  return win;
}

async function loadOfficialExporter(win) {
  const result = await esbuild.build({
    stdin: {
      contents: `
        import { exportToSvg, restoreElements } from "@excalidraw/excalidraw";
        globalThis.__EXCALIDRAW_OFFICIAL_EXPORT__ = { exportToSvg, restoreElements };
      `,
      resolveDir: packageDir,
      sourcefile: "official-export-entry.js",
    },
    bundle: true,
    format: "iife",
    platform: "browser",
    write: false,
    logLevel: "silent",
  });

  win.eval(result.outputFiles[0].text);
  return win.__EXCALIDRAW_OFFICIAL_EXPORT__;
}

function dedupeRootSvgAttributes(serialized) {
  return serialized.replace(/^<svg\b([^>]*)>/, (match, attrs) => {
    const seen = new Set();
    const cleanedAttrs = attrs.replace(
      /(\s+)([A-Za-z_][\w:.-]*)(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?/g,
      (attrMatch, leading, name) => {
        if (seen.has(name)) {
          return "";
        }
        seen.add(name);
        return attrMatch;
      },
    );
    return `<svg${cleanedAttrs}>`;
  });
}

async function main() {
  const [, , inputArg, outputArg] = process.argv;
  if (!inputArg || !outputArg) {
    usage();
    process.exit(2);
  }

  const input = path.resolve(inputArg);
  const output = path.resolve(outputArg);
  const prodDir = path.join(packageDir, "node_modules", "@excalidraw", "excalidraw", "dist", "prod");
  const win = installDom(prodDir);
  const official = await loadOfficialExporter(win);
  const scene = JSON.parse(await fs.promises.readFile(input, "utf8"));
  const elements = official.restoreElements(scene.elements || [], null);
  const svg = await official.exportToSvg({
    elements,
    appState: {
      ...scene.appState,
      exportBackground: scene.appState?.exportBackground ?? true,
      viewBackgroundColor: scene.appState?.viewBackgroundColor || "#ffffff",
    },
    files: scene.files || {},
    exportPadding: scene.appState?.exportPadding ?? 40,
  });
  const serialized = dedupeRootSvgAttributes(new win.XMLSerializer().serializeToString(svg));
  await fs.promises.mkdir(path.dirname(output), { recursive: true });
  await fs.promises.writeFile(output, serialized.endsWith("\n") ? serialized : `${serialized}\n`, "utf8");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

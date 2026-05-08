import {
  parse
} from "./chunk-BWRV6VQG.js";
import "./chunk-QU3K4WYA.js";
import "./chunk-S5D6MDOA.js";
import "./chunk-LNU77GRU.js";
import "./chunk-LAPH2MTR.js";
import "./chunk-F2HMK7RH.js";
import "./chunk-7HPTRVKH.js";
import "./chunk-NOMSY45I.js";
import "./chunk-PY3Z4IIO.js";
import "./chunk-677JRFFP.js";
import "./chunk-Q6Z7EPY6.js";
import {
  selectSvgElement
} from "./chunk-A3VBLLP2.js";
import "./chunk-MGS2F3ZJ.js";
import "./chunk-F2MXYUQQ.js";
import {
  configureSvgSize
} from "./chunk-VOZCMLBU.js";
import "./chunk-5P6B6HFW.js";
import {
  __name,
  log
} from "./chunk-MD6LXWSN.js";
import "./chunk-256EKJAK.js";

// ../../node_modules/mermaid/dist/chunks/mermaid.core/infoDiagram-42DDH7IO.mjs
var parser = {
  parse: __name(async (input) => {
    const ast = await parse("info", input);
    log.debug(ast);
  }, "parse")
};
var DEFAULT_INFO_DB = {
  version: "11.14.0" + (true ? "" : "-tiny")
};
var getVersion = __name(() => DEFAULT_INFO_DB.version, "getVersion");
var db = {
  getVersion
};
var draw = __name((text, id, version) => {
  log.debug("rendering info diagram\n" + text);
  const svg = selectSvgElement(id);
  configureSvgSize(svg, 100, 400, true);
  const group = svg.append("g");
  group.append("text").attr("x", 100).attr("y", 40).attr("class", "version").attr("font-size", 32).style("text-anchor", "middle").text(`v${version}`);
}, "draw");
var renderer = { draw };
var diagram = {
  parser,
  db,
  renderer
};
export {
  diagram
};
//# sourceMappingURL=infoDiagram-42DDH7IO-O6ZJZOHX.js.map

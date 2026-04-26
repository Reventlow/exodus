/* =============================================================
 * BLACKLOG.NET // EXODUS — Clearance Gate
 * Vanilla-JS port of the React prototype in design_handoff/login.jsx.
 * Drives the multi-stage state machine, the agency-map / code-rain
 * canvas backdrop, the side rails, header strip, footer strip,
 * scramble effect, typewriter and the AJAX login submit.
 *
 * This file expects:
 *   window.LOGIN_TWEAKS = { ...SiteSettings.tweaks }       (required)
 *   window.LOGIN_CONFIG = { csrfToken, loginUrl, registerUrl,
 *                           nextUrl, mode: 'login' | 'register',
 *                           username: '<current user, optional>' }
 * ============================================================= */
(function () {
  "use strict";

  // -----------------------------------------------------------
  // Configuration & palettes
  // -----------------------------------------------------------
  var TWEAKS = Object.assign({
    palette: "emerald",
    backdrop: "ops_map",
    map_intensity: 1.0,
    show_radar: true,
    show_nodes: true,
    rain_style: "katakana",
    rain_density: 1.0,
    rain_speed: 1.0,
    scanlines: true,
    vignette: true,
    show_rails: true,
    agency_name: "BLACKLOG.NET",
    op_codename: "OMEGA-7",
  }, window.LOGIN_TWEAKS || {});

  var CONFIG = Object.assign({
    csrfToken: "",
    loginUrl: "/accounts/login/",
    registerUrl: "/accounts/register/",
    nextUrl: "/",
    mode: "login",       // "login" | "register"
    username: "",
  }, window.LOGIN_CONFIG || {});

  var PALETTES = {
    emerald: { name: "EMERALD", primary: "#39ff7a", dim: "#0e3a1f",
               glow: "rgba(57,255,122,0.55)", soft: "rgba(57,255,122,0.10)" },
    amber:   { name: "AMBER",   primary: "#ffb454", dim: "#3a2410",
               glow: "rgba(255,180,84,0.50)", soft: "rgba(255,180,84,0.10)" },
    ice:     { name: "ICE",     primary: "#7fdcff", dim: "#0e2a3a",
               glow: "rgba(127,220,255,0.50)", soft: "rgba(127,220,255,0.10)" },
    blood:   { name: "BLOOD",   primary: "#ff4d5e", dim: "#3a0e16",
               glow: "rgba(255,77,94,0.50)", soft: "rgba(255,77,94,0.10)" },
    bone:    { name: "BONE",    primary: "#e8e2cf", dim: "#2a2820",
               glow: "rgba(232,226,207,0.40)", soft: "rgba(232,226,207,0.08)" },
  };
  var PALETTE = PALETTES[TWEAKS.palette] || PALETTES.emerald;

  // Continent silhouettes (low-poly, normalized 0..1).
  var CONTINENTS = [
    [[0.10,0.22],[0.22,0.18],[0.30,0.22],[0.31,0.30],[0.27,0.36],
     [0.22,0.46],[0.18,0.50],[0.13,0.46],[0.09,0.40],[0.07,0.32],[0.08,0.26]],
    [[0.24,0.50],[0.30,0.52],[0.32,0.58],[0.30,0.68],[0.28,0.78],
     [0.26,0.86],[0.24,0.80],[0.23,0.70],[0.24,0.60]],
    [[0.46,0.22],[0.54,0.20],[0.58,0.24],[0.56,0.30],[0.52,0.34],
     [0.48,0.32],[0.45,0.28]],
    [[0.48,0.36],[0.56,0.36],[0.60,0.44],[0.58,0.56],[0.54,0.66],
     [0.50,0.72],[0.46,0.62],[0.46,0.50],[0.47,0.42]],
    [[0.58,0.20],[0.74,0.18],[0.84,0.24],[0.86,0.32],[0.80,0.40],
     [0.72,0.42],[0.66,0.40],[0.60,0.36],[0.58,0.28]],
    [[0.78,0.46],[0.84,0.48],[0.88,0.52],[0.84,0.56],[0.80,0.54]],
    [[0.80,0.66],[0.90,0.66],[0.92,0.74],[0.86,0.78],[0.80,0.74]],
  ];

  var NODES = [
    { x: 0.18, y: 0.32, label: "BOG-04", status: "active"  },
    { x: 0.21, y: 0.40, label: "MEX-12", status: "standby" },
    { x: 0.27, y: 0.66, label: "SAO-01", status: "active"  },
    { x: 0.49, y: 0.24, label: "REY-07", status: "active"  },
    { x: 0.52, y: 0.28, label: "PRG-04", status: "active"  },
    { x: 0.55, y: 0.31, label: "MAR-09", status: "burned"  },
    { x: 0.51, y: 0.40, label: "TUN-02", status: "dormant" },
    { x: 0.59, y: 0.50, label: "NRB-11", status: "active"  },
    { x: 0.66, y: 0.34, label: "TBL-03", status: "standby" },
    { x: 0.71, y: 0.28, label: "MOW-08", status: "dormant" },
    { x: 0.78, y: 0.30, label: "BJS-06", status: "active"  },
    { x: 0.82, y: 0.36, label: "HKG-02", status: "active"  },
    { x: 0.86, y: 0.50, label: "JKT-05", status: "standby" },
    { x: 0.86, y: 0.72, label: "SYD-01", status: "active"  },
  ];

  function statusColor(status, p) {
    if (status === "active")  return p.primary;
    if (status === "standby") return "#ffb454";
    if (status === "dormant") return "#6c8aa0";
    if (status === "burned")  return "#ff4d5e";
    return p.primary;
  }

  // -----------------------------------------------------------
  // Helpers: DOM lookup, text ops
  // -----------------------------------------------------------
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function pad(n, w) {
    var s = String(n);
    while (s.length < w) s = "0" + s;
    return s;
  }

  function utcFmt(d) {
    return d.toISOString().replace("T", " ").slice(0, 19) + "Z";
  }

  // -----------------------------------------------------------
  // Backdrop: AGENCY MAP
  // -----------------------------------------------------------
  function pointInPoly(x, y, poly) {
    var inside = false;
    for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      var xi = poly[i][0], yi = poly[i][1];
      var xj = poly[j][0], yj = poly[j][1];
      var hit = ((yi > y) !== (yj > y)) &&
                (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi);
      if (hit) inside = !inside;
    }
    return inside;
  }
  function pointInAnyContinent(x, y) {
    for (var i = 0; i < CONTINENTS.length; i++) {
      if (pointInPoly(x, y, CONTINENTS[i])) return true;
    }
    return false;
  }

  function startAgencyMap(canvas, opts) {
    var ctx = canvas.getContext("2d");
    var dpr = window.devicePixelRatio || 1;
    var W = 0, H = 0;
    var dots = [];
    var arcs = [];
    var startTime = performance.now();
    var rafId = 0;
    var arcTimer = 0;
    var palette = opts.palette;
    var intensity = opts.intensity;
    var showRadar = opts.show_radar;
    var showNodes = opts.show_nodes;

    function mapBox() {
      var mw = Math.min(W * 0.92, 1400);
      var mh = mw * 0.5;
      var mx = (W - mw) / 2;
      var my = (H - mh) / 2 + 20;
      return { mx: mx, my: my, mw: mw, mh: mh };
    }
    function buildDots() {
      var box = mapBox();
      dots = [];
      var step = 8;
      for (var y = 0; y < box.mh; y += step) {
        for (var x = 0; x < box.mw; x += step) {
          var nx = x / box.mw, ny = y / box.mh;
          if (pointInAnyContinent(nx, ny)) {
            // pseudo-random sparseness
            var n = (Math.sin(x * 12.9898 + y * 78.233) * 43758.5453) % 1;
            if (n > -0.85) dots.push([box.mx + x, box.my + y]);
          }
        }
      }
    }

    function resize() {
      W = canvas.clientWidth;
      H = canvas.clientHeight;
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      buildDots();
    }
    resize();
    var ro = new ResizeObserver(resize);
    ro.observe(canvas);

    function scheduleArc() {
      if (NODES.length < 2) return;
      var a = NODES[Math.floor(Math.random() * NODES.length)];
      var b = a;
      while (b === a) b = NODES[Math.floor(Math.random() * NODES.length)];
      arcs.push({ a: a, b: b, t0: performance.now(),
                  dur: 1400 + Math.random() * 1400 });
    }
    arcTimer = setInterval(scheduleArc, 1100);

    function tick(now) {
      var t = (now - startTime) / 1000;
      ctx.clearRect(0, 0, W, H);
      var box = mapBox();
      var mx = box.mx, my = box.my, mw = box.mw, mh = box.mh;
      var c = palette.primary;

      // background grid
      ctx.save();
      ctx.strokeStyle = c + "18";
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (var gx = 0; gx <= W; gx += 40) {
        ctx.moveTo(gx + 0.5, 0); ctx.lineTo(gx + 0.5, H);
      }
      for (var gy = 0; gy <= H; gy += 40) {
        ctx.moveTo(0, gy + 0.5); ctx.lineTo(W, gy + 0.5);
      }
      ctx.stroke();
      ctx.restore();

      // dashed map guides
      ctx.save();
      ctx.strokeStyle = c + "30";
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 6]);
      [0.25, 0.5, 0.75].forEach(function (f) {
        var yy = my + mh * f;
        ctx.beginPath(); ctx.moveTo(mx, yy); ctx.lineTo(mx + mw, yy); ctx.stroke();
      });
      [0.25, 0.5, 0.75].forEach(function (f) {
        var xx = mx + mw * f;
        ctx.beginPath(); ctx.moveTo(xx, my); ctx.lineTo(xx, my + mh); ctx.stroke();
      });
      ctx.setLineDash([]);
      ctx.restore();

      // continents (dot grid)
      ctx.save();
      ctx.fillStyle = c + "55";
      for (var i = 0; i < dots.length; i++) {
        ctx.fillRect(dots[i][0], dots[i][1], 1.6, 1.6);
      }
      ctx.restore();

      // radar sweep
      if (showRadar) {
        var focal = NODES[4];
        var cx = mx + focal.x * mw;
        var cy = my + focal.y * mh;
        var sweep = (t * 0.6) % (Math.PI * 2);
        ctx.save();
        ctx.strokeStyle = c + "22";
        ctx.lineWidth = 1;
        [60, 120, 200, 300].forEach(function (r) {
          ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
        });
        var grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, 320);
        grad.addColorStop(0, c + "44");
        grad.addColorStop(1, c + "00");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, 320, sweep - 0.45, sweep);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = c + "AA";
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.cos(sweep) * 320, cy + Math.sin(sweep) * 320);
        ctx.stroke();
        ctx.restore();
      }

      // arcs (cull expired)
      arcs = arcs.filter(function (a) { return now - a.t0 < a.dur; });
      ctx.save();
      for (var ai = 0; ai < arcs.length; ai++) {
        var arc = arcs[ai];
        var p = (now - arc.t0) / arc.dur;
        var ax = mx + arc.a.x * mw, ay = my + arc.a.y * mh;
        var bx = mx + arc.b.x * mw, by = my + arc.b.y * mh;
        var ccx = (ax + bx) / 2;
        var ccy = (ay + by) / 2 - Math.hypot(bx - ax, by - ay) * 0.25;
        ctx.strokeStyle = c + "33";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.quadraticCurveTo(ccx, ccy, bx, by);
        ctx.stroke();
        var tt = Math.min(1, p);
        var qx = (1 - tt) * (1 - tt) * ax + 2 * (1 - tt) * tt * ccx + tt * tt * bx;
        var qy = (1 - tt) * (1 - tt) * ay + 2 * (1 - tt) * tt * ccy + tt * tt * by;
        ctx.fillStyle = c;
        ctx.shadowColor = c;
        ctx.shadowBlur = 10;
        ctx.beginPath();
        ctx.arc(qx, qy, 2.4, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
      }
      ctx.restore();

      // nodes
      if (showNodes) {
        ctx.save();
        ctx.font = '10px "JetBrains Mono", monospace';
        ctx.textBaseline = "middle";
        for (var ni = 0; ni < NODES.length; ni++) {
          var n = NODES[ni];
          var nx = mx + n.x * mw, ny = my + n.y * mh;
          var col = statusColor(n.status, palette);
          if (n.status === "active") {
            var phase = (Math.sin(t * 2 + n.x * 7 + n.y * 11) + 1) / 2;
            ctx.strokeStyle = col + "AA";
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(nx, ny, 4 + phase * 6, 0, Math.PI * 2);
            ctx.stroke();
          }
          ctx.strokeStyle = col + "66";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(nx - 8, ny); ctx.lineTo(nx - 3, ny);
          ctx.moveTo(nx + 3, ny); ctx.lineTo(nx + 8, ny);
          ctx.moveTo(nx, ny - 8); ctx.lineTo(nx, ny - 3);
          ctx.moveTo(nx, ny + 3); ctx.lineTo(nx, ny + 8);
          ctx.stroke();
          ctx.fillStyle = col;
          ctx.shadowColor = col;
          ctx.shadowBlur = 8;
          ctx.beginPath();
          ctx.arc(nx, ny, 2.4, 0, Math.PI * 2);
          ctx.fill();
          ctx.shadowBlur = 0;
          ctx.fillStyle = col + "AA";
          ctx.fillText(n.label, nx + 10, ny - 0.5);
        }
        ctx.restore();
      }

      // focal crosshair
      var foc = NODES[4];
      var fx = mx + foc.x * mw;
      var fy = my + foc.y * mh;
      ctx.save();
      ctx.strokeStyle = c + "AA";
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 4]);
      ctx.beginPath();
      ctx.moveTo(mx, fy); ctx.lineTo(fx - 14, fy);
      ctx.moveTo(fx + 14, fy); ctx.lineTo(mx + mw, fy);
      ctx.moveTo(fx, my); ctx.lineTo(fx, fy - 14);
      ctx.moveTo(fx, fy + 14); ctx.lineTo(fx, my + mh);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();

      // map frame brackets
      ctx.save();
      ctx.strokeStyle = c + "AA";
      ctx.lineWidth = 1.2;
      var k = 18;
      var corners = [
        [mx, my, 1, 1],
        [mx + mw, my, -1, 1],
        [mx, my + mh, 1, -1],
        [mx + mw, my + mh, -1, -1],
      ];
      corners.forEach(function (cn) {
        ctx.beginPath();
        ctx.moveTo(cn[0], cn[1] + cn[3] * k);
        ctx.lineTo(cn[0], cn[1]);
        ctx.lineTo(cn[0] + cn[2] * k, cn[1]);
        ctx.stroke();
      });
      ctx.restore();

      // metadata text
      ctx.save();
      ctx.fillStyle = c + "AA";
      ctx.font = '9px "JetBrains Mono", monospace';
      ctx.fillText("MERCATOR  //  GLOBAL OPS GRID", mx + 8, my - 8);
      ctx.textAlign = "right";
      var activeCount = NODES.filter(function (n) { return n.status === "active"; }).length;
      ctx.fillText("NODES " + NODES.length + "  //  ACTIVE " + activeCount,
                   mx + mw - 8, my - 8);
      ctx.textAlign = "left";
      ctx.fillStyle = c + "66";
      ctx.fillText("UTC " + new Date().toISOString().slice(11, 19),
                   mx + 8, my + mh + 14);
      ctx.textAlign = "right";
      ctx.fillText("LAT 0.000  LON 0.000  // SPOOFED", mx + mw - 8, my + mh + 14);
      ctx.restore();

      // dim pass
      ctx.save();
      ctx.fillStyle = "rgba(0,0,0," + (0.45 - 0.15 * intensity) + ")";
      ctx.fillRect(0, 0, W, H);
      ctx.restore();

      rafId = requestAnimationFrame(tick);
    }
    rafId = requestAnimationFrame(tick);

    return function stop() {
      cancelAnimationFrame(rafId);
      clearInterval(arcTimer);
      ro.disconnect();
    };
  }

  // -----------------------------------------------------------
  // Backdrop: CODE RAIN
  // -----------------------------------------------------------
  function startCodeRain(canvas, opts) {
    var ctx = canvas.getContext("2d");
    var dpr = window.devicePixelRatio || 1;
    var KATAKANA = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉ";
    var HEX = "0123456789ABCDEF";
    var BIN = "01";
    var ASCII = "!@#$%&*()_+-=[]{}<>?/\\|~`abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    var charset = opts.style === "hex" ? HEX :
                  opts.style === "binary" ? BIN :
                  opts.style === "ascii" ? ASCII : KATAKANA;
    var fontSize = 16;
    var cols = 0, drops = [], chars = [];
    var rafId = 0, last = performance.now();

    function resize() {
      var w = canvas.clientWidth, h = canvas.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      cols = Math.ceil(w / fontSize);
      drops = []; chars = [];
      for (var i = 0; i < cols; i++) {
        drops.push(Math.random() * -50);
        chars.push(charset[Math.floor(Math.random() * charset.length)]);
      }
      ctx.font = (fontSize * dpr) + "px \"JetBrains Mono\", \"Courier New\", monospace";
      ctx.textBaseline = "top";
    }
    resize();
    var ro = new ResizeObserver(resize);
    ro.observe(canvas);

    function tick(now) {
      var dt = Math.min(50, now - last);
      last = now;
      ctx.fillStyle = "rgba(2,8,5,0.08)";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      for (var i = 0; i < cols; i++) {
        var y = drops[i] * fontSize;
        ctx.fillStyle = opts.color;
        ctx.shadowColor = opts.color;
        ctx.shadowBlur = 8 * dpr;
        if (Math.random() < 0.04) {
          chars[i] = charset[Math.floor(Math.random() * charset.length)];
        }
        ctx.fillText(chars[i], i * fontSize * dpr, y * dpr);
        ctx.shadowBlur = 0;
        ctx.fillStyle = opts.color + "44";
        for (var tIdx = 1; tIdx < 6; tIdx++) {
          ctx.fillText(charset[(i + tIdx) % charset.length],
                       i * fontSize * dpr, (y - tIdx * fontSize) * dpr);
        }
        drops[i] += (0.4 + Math.random() * 0.6) * opts.speed * (dt / 16.6);
        if (y > canvas.clientHeight && Math.random() > 1 - 0.02 * opts.density) {
          drops[i] = -Math.random() * 30;
        }
      }
      rafId = requestAnimationFrame(tick);
    }
    rafId = requestAnimationFrame(tick);
    return function stop() { cancelAnimationFrame(rafId); ro.disconnect(); };
  }

  // -----------------------------------------------------------
  // Side rails (telemetry log)
  // -----------------------------------------------------------
  var RAIL_LINES = [
    "// node 7 handshake ok", "// uplink: TOR/relay-04",
    "// AES-256-GCM verified", "// keystroke entropy 0.94",
    "// sweeping ports 22,80,443", "// honeypot: clean",
    "// signal route: hk → fra → bog", "// ICE thread: dormant",
    "// last breach: 47d 12h", "// dead drop: 03 active",
    "// payload chunk 0x3F ack", "// telemetry stripped",
    "// geo: spoofed (lat 0, lon 0)", "// container: ephemeral",
    "// fingerprint: rotated", "// deniability: enabled",
    "// audit: zero-knowledge", "// sat link: degraded",
    "// noise floor -84dBm", "// burner key: ready",
  ];

  function startRail(el) {
    if (!el) return function () {};
    var tick = 0;
    function render() {
      var start = tick % RAIL_LINES.length;
      var html = "";
      for (var i = 0; i < 14; i++) {
        var line = RAIL_LINES[(start + i) % RAIL_LINES.length];
        var op = (0.25 + (i / 14) * 0.75).toFixed(2);
        var idx = pad((tick + i) % 9999, 4);
        html += "<span class=\"rail-line\" style=\"opacity:" + op + "\">" +
                "<span class=\"muted\">[" + idx + "]</span> " + escapeHtml(line) +
                "</span>";
      }
      el.innerHTML = html;
    }
    render();
    var id = setInterval(function () { tick++; render(); }, 700);
    return function stop() { clearInterval(id); };
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c];
    });
  }

  // -----------------------------------------------------------
  // Header strip & footer (live UTC clock, ops counter)
  // -----------------------------------------------------------
  function startHeader(strip, sessionId) {
    var sesEl = $(".strip-ses", strip);
    var opsEl = $(".strip-ops", strip);
    var utcEl = $(".strip-utc", strip);
    var glyphs = "ABCDEF0123456789#%&*+-/=";
    var locked = false;
    var opCount = 127;
    var frame = 0;
    var rafId = 0;
    function frameTick() {
      frame++;
      if (sesEl && !locked && frame % 2 === 0) {
        var s = "";
        for (var i = 0; i < sessionId.length; i++) {
          s += sessionId[i] === " " ? " " :
               glyphs[Math.floor(Math.random() * glyphs.length)];
        }
        sesEl.textContent = s;
      }
      rafId = requestAnimationFrame(frameTick);
    }
    rafId = requestAnimationFrame(frameTick);

    // After ~1.4s lock the session id to its real value.
    setTimeout(function () { locked = true; if (sesEl) sesEl.textContent = sessionId; }, 1400);

    function refresh() {
      if (utcEl) utcEl.textContent = utcFmt(new Date());
      if (opsEl) {
        if (Math.random() < 0.2) {
          opCount = Math.max(110, Math.min(180,
            opCount + (Math.random() < 0.5 ? -1 : 1)));
        }
        opsEl.textContent = pad(opCount, 3);
      }
    }
    refresh();
    var id = setInterval(refresh, 1000);
    return function stop() { clearInterval(id); cancelAnimationFrame(rafId); };
  }

  function setFooterStage(footEl, stage) {
    var labels = {
      boot:        "BOOTING",
      login:       "AWAITING CLEARANCE",
      authing:     "AUTHENTICATING",
      granted:     "ACCESS GRANTED",
      denied:      "ACCESS DENIED",
      requestForm: "PETITION FORM",
    };
    var stageEl = $(".foot-stage", footEl);
    if (stageEl) stageEl.textContent = labels[stage] || stage.toUpperCase();
  }

  // -----------------------------------------------------------
  // Typewriter (writes text into a single element)
  // -----------------------------------------------------------
  function typewriter(el, text, speed) {
    el.textContent = "";
    var i = 0;
    var id = setInterval(function () {
      i++;
      el.textContent = text.slice(0, i);
      if (i >= text.length) clearInterval(id);
    }, speed);
    return function () { clearInterval(id); el.textContent = text; };
  }

  // -----------------------------------------------------------
  // Stage management
  // -----------------------------------------------------------
  var stages = {};
  function showStage(name) {
    Object.keys(stages).forEach(function (k) {
      if (stages[k]) stages[k].hidden = (k !== name);
    });
    setFooterStage($(".foot"), name);
    if (name === "login") {
      // Refocus first input for keyboard-first users.
      var f = $("#field-codename");
      if (f) try { f.focus(); } catch (e) {}
    }
  }

  // -----------------------------------------------------------
  // Boot sequence
  // -----------------------------------------------------------
  var BOOT_SCRIPT = [
    "[BIOS] BLACKLOG TERMINAL v8.14.32  ©  ████████",
    "[OK] CPU INIT ······················ 12 CORES",
    "[OK] CRYPTO MODULE ················· LOADED",
    "[OK] ENTROPY POOL ·················· /dev/urandom",
    "[OK] SECURE ENCLAVE ················ SEALED",
    "[..] LOCATING UPLINK NODE ·········· ",
    "[OK] UPLINK ESTABLISHED ············ NODE-07",
    "[..] HANDSHAKE                       ",
    "[OK] HANDSHAKE ····················· VERIFIED",
    "[OK] WIPING TELEMETRY ··············· DONE",
    "",
    "    WELCOME, OPERATIVE.",
    "    CLEARANCE GATE INITIALIZED.",
    "",
  ];

  function runBoot(onDone) {
    var pre = $("#boot-pre");
    if (!pre) { onDone(); return; }
    pre.innerHTML = "";
    var i = 0;
    var id = setInterval(function () {
      var line = BOOT_SCRIPT[i];
      var div = document.createElement("div");
      div.className = "boot-line";
      div.textContent = line;
      pre.appendChild(div);
      i++;
      if (i >= BOOT_SCRIPT.length) {
        clearInterval(id);
        var caretLine = document.createElement("div");
        caretLine.className = "boot-line";
        caretLine.innerHTML = "&gt; _<span class=\"caret-inline blink\"></span>";
        pre.appendChild(caretLine);
        setTimeout(onDone, 350);
      }
    }, 90);
  }

  // -----------------------------------------------------------
  // Auth cinematic (after server confirms success)
  // -----------------------------------------------------------
  var AUTH_STEPS = [
    { t: 0,    label: "INIT SECURE CHANNEL",   detail: "negotiating TLS-1.3 // SNI cloaked" },
    { t: 350,  label: "RESOLVING DEAD DROP",   detail: "hop 3 of 7 // latency 84ms" },
    { t: 750,  label: "VERIFYING CODENAME",    detail: "matched against ledger //" },
    { t: 1150, label: "DERIVING KEY",          detail: "argon2id // mem 64MiB t=3" },
    { t: 1700, label: "CHALLENGE / RESPONSE",  detail: "HMAC-SHA512 // OK" },
    { t: 2100, label: "SWEEPING TELEMETRY",    detail: "5 trackers neutralized" },
    { t: 2450, label: "BIOMETRIC LIFT",        detail: "keystroke pattern within 0.94 confidence" },
    { t: 2800, label: "CLEARANCE GRANTED",     detail: "session token issued // valid 4h" },
  ];

  function renderAuthSteps(codename) {
    var head = $(".auth-codename");
    if (head) head.textContent = codename || "OPERATIVE";
    var list = $("#auth-list");
    if (!list) return;
    list.innerHTML = "";
    AUTH_STEPS.forEach(function (s, i) {
      var row = document.createElement("div");
      row.className = "auth-step pending";
      row.dataset.idx = String(i);
      row.innerHTML =
        "<span class=\"auth-marker\">[   ]</span>" +
        "<span class=\"auth-label\">" + escapeHtml(s.label) + "</span>" +
        "<span class=\"auth-fill\"></span>" +
        "<span class=\"auth-detail\">" + escapeHtml(s.detail) + "</span>";
      list.appendChild(row);
    });
  }
  function runAuthCinematic(codename, onDone) {
    renderAuthSteps(codename);
    var bar = $("#auth-bar-fill");
    var rows = $$("#auth-list .auth-step");
    var timeouts = [];
    AUTH_STEPS.forEach(function (s, i) {
      timeouts.push(setTimeout(function () {
        rows.forEach(function (r, ri) {
          r.classList.remove("active");
          if (ri < i) {
            r.classList.remove("pending");
            r.classList.add("done");
            var m = $(".auth-marker", r);
            if (m) m.textContent = "[ ✓ ]";
          } else if (ri === i) {
            r.classList.remove("pending", "done");
            r.classList.add("active");
            var ma = $(".auth-marker", r);
            if (ma) ma.textContent = "[···]";
          }
        });
        if (bar) bar.style.width = (((i + 1) / AUTH_STEPS.length) * 100) + "%";
      }, s.t));
    });
    timeouts.push(setTimeout(function () {
      rows.forEach(function (r) {
        r.classList.remove("active", "pending");
        r.classList.add("done");
        var m = $(".auth-marker", r);
        if (m) m.textContent = "[ ✓ ]";
      });
      if (bar) bar.style.width = "100%";
      onDone();
    }, 3300));
    return function abort() { timeouts.forEach(clearTimeout); };
  }

  // -----------------------------------------------------------
  // Granted / Denied panels
  // -----------------------------------------------------------
  function showGranted(codename, onContinue) {
    showStage("granted");
    var pre = $("#granted-pre");
    if (!pre) return;
    var lines = [
      "ACCESS GRANTED.",
      "",
      "OPERATIVE: " + (codename || "UNNAMED").toUpperCase(),
      "CLEARANCE: TIER-3 // DIRECTORATE " + TWEAKS.agency_name,
      "PROJECT:   " + TWEAKS.op_codename,
      "",
      "PENDING BRIEFINGS:",
      "  ▸ NIGHTSHADE PROTOCOL  (priority: red)",
      "  ▸ ASSET TRANSFER 09-X   (priority: amber)",
      "  ▸ DEAD DROP PRAGUE-04   (priority: green)",
      "",
      "WELCOME BACK, OPERATIVE.",
      "STAY DARK.",
    ];
    pre.innerHTML = "";
    var idx = 0;
    var id = setInterval(function () {
      var div = document.createElement("div");
      div.textContent = lines[idx];
      pre.appendChild(div);
      idx++;
      if (idx >= lines.length) {
        clearInterval(id);
        var caret = document.createElement("div");
        caret.innerHTML = "&gt; _<span class=\"caret-inline blink\"></span>";
        pre.appendChild(caret);
      }
    }, 110);

    var btn = $("#granted-btn");
    if (btn) {
      btn.onclick = function () {
        if (onContinue) onContinue();
      };
    }
  }
  function showDenied(reason, attempts) {
    showStage("denied");
    var t = $("#denied-log");
    if (t) {
      var ses = Math.random().toString(16).slice(2, 8).toUpperCase();
      t.textContent =
        "!! HANDSHAKE FAILED\n" +
        "!! " + (reason || "UNKNOWN FAULT") + "\n" +
        "!! INCIDENT LOGGED — SES " + ses + "\n" +
        (attempts >= 3 ? "!! TERMINAL FROZEN — 30s COOLDOWN"
                       : "!! YOU MAY RETRY") + "\n";
    }
  }

  // -----------------------------------------------------------
  // Side panel: roster, threats, broadcast (login mode only)
  // -----------------------------------------------------------
  function startSidePanel() {
    var threatRow = $$("#threats .threat");
    var basePcts = [22, 9, 14, 88];
    var tick = 0;
    function refreshThreats() {
      threatRow.forEach(function (row, i) {
        var wob = (Math.sin((tick + i) * 1.3) * 4) | 0;
        var p = Math.max(0, Math.min(100, basePcts[i] + wob));
        var fill = $(".threat-fill", row);
        var lbl = $(".threat-pct", row);
        if (fill) fill.style.width = p + "%";
        if (lbl) lbl.textContent = pad(p, 2) + "%";
      });
    }
    refreshThreats();
    var id = setInterval(function () { tick++; refreshThreats(); }, 2000);

    // Scramble broadcast lines
    var bc = $$(".bc-scramble");
    var glyphs = "ABCDEF0123456789#%&*+-/=";
    var frame = 0;
    var rafId = 0;
    function tickFrame() {
      frame++;
      if (frame % 2 === 0) {
        bc.forEach(function (el) {
          var src = el.dataset.value || el.textContent;
          el.dataset.value = src;
          var s = "";
          for (var i = 0; i < src.length; i++) {
            s += src[i] === " " ? " " :
                 glyphs[Math.floor(Math.random() * glyphs.length)];
          }
          el.textContent = s;
        });
      }
      rafId = requestAnimationFrame(tickFrame);
    }
    rafId = requestAnimationFrame(tickFrame);
    return function stop() { clearInterval(id); cancelAnimationFrame(rafId); };
  }

  // -----------------------------------------------------------
  // Login flow
  // -----------------------------------------------------------
  var attempts = 0;
  var lockoutUntil = 0;
  var lockoutTimer = 0;

  function refreshLockoutBanner() {
    var banner = $("#login-locked");
    var btn = $("#login-submit");
    var attemptsEl = $("#login-attempts");
    var left = Math.max(0, Math.ceil((lockoutUntil - Date.now()) / 1000));
    if (attemptsEl) attemptsEl.textContent = "ATTEMPTS " + attempts + "/3";
    if (left > 0) {
      if (banner) {
        banner.hidden = false;
        banner.innerHTML = "<span class=\"err-tag\">!! LOCKED</span> " +
          "TERMINAL FROZEN — RETRY IN " + pad(left, 2) + "s";
      }
      if (btn) {
        btn.disabled = true;
        var span = $("span:nth-child(2)", btn);
        if (span) span.textContent = "TERMINAL FROZEN";
      }
    } else {
      if (banner) banner.hidden = true;
      if (btn) {
        btn.disabled = false;
        var span2 = $("span:nth-child(2)", btn);
        if (span2) span2.textContent = "INITIATE AUTHENTICATION";
      }
      if (lockoutTimer) { clearInterval(lockoutTimer); lockoutTimer = 0; }
    }
  }

  function setError(msg) {
    var box = $("#login-error");
    if (!box) return;
    if (msg) {
      box.hidden = false;
      box.innerHTML = "<span class=\"err-tag\">!! ERROR</span> " + escapeHtml(msg);
    } else {
      box.hidden = true;
      box.innerHTML = "";
    }
  }

  function clientValidate(codename, passphrase) {
    if (!codename.trim()) return "CODENAME REQUIRED.";
    if (passphrase.length < 4) return "PASSPHRASE TOO SHORT. MINIMUM 4 CHARACTERS.";
    return null;
  }

  function submitLogin(form, ev) {
    if (Date.now() < lockoutUntil) {
      ev.preventDefault();
      return;
    }
    var codename = form.username.value;
    var passphrase = form.password.value;
    var err = clientValidate(codename, passphrase);
    if (err) {
      ev.preventDefault();
      setError(err);
      return;
    }
    setError(null);

    // Use AJAX so we can play the cinematic AFTER the server confirms.
    ev.preventDefault();
    var fd = new FormData(form);
    fetch(CONFIG.loginUrl + (CONFIG.nextUrl ? "?next=" + encodeURIComponent(CONFIG.nextUrl) : ""), {
      method: "POST",
      headers: {
        "X-CSRFToken": CONFIG.csrfToken,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
      },
      body: fd,
      credentials: "same-origin",
    }).then(function (r) {
      // Try JSON; fall back to redirect if server returned HTML.
      var ct = r.headers.get("content-type") || "";
      if (ct.indexOf("application/json") !== -1) {
        return r.json().then(function (data) { return { ok: r.ok, data: data }; });
      }
      // Non-JSON response (e.g., a server-side redirect followed by HTML).
      // Treat 2xx with no JSON as success and reload to trigger the redirect.
      if (r.ok) return { ok: true, data: { redirect: CONFIG.nextUrl || "/" } };
      return { ok: false, data: { error: "ACCESS DENIED. Invalid credentials." } };
    }).then(function (resp) {
      if (resp.ok && resp.data && resp.data.ok !== false) {
        var redir = (resp.data && resp.data.redirect) || CONFIG.nextUrl || "/";
        // Cinematic playback then jump.
        showStage("authing");
        runAuthCinematic(codename, function () {
          showGranted(codename, function () {
            window.location = redir;
          });
        });
      } else {
        attempts += 1;
        var reason = (resp.data && resp.data.error) || "ACCESS DENIED. Invalid credentials.";
        if (attempts >= 3) {
          lockoutUntil = Date.now() + 30000;
          if (lockoutTimer) clearInterval(lockoutTimer);
          lockoutTimer = setInterval(refreshLockoutBanner, 250);
        }
        showStage("authing");
        runAuthCinematic(codename, function () {
          showDenied(reason, attempts);
        });
      }
    }).catch(function () {
      // Network error — still play denied without locking out aggressively.
      showDenied("UPLINK SEVERED. CHECK CONNECTION.", attempts);
    });
  }

  function submitRegister(form, ev) {
    var u = form.username.value.trim();
    var p1 = form.password.value;
    var p2 = form.password_confirm.value;
    var errs = [];
    if (!u) errs.push("Codename is required.");
    if (p1.length < 8) errs.push("Passphrase must be at least 8 characters.");
    if (p1 !== p2) errs.push("Passphrases do not match.");
    if (errs.length) {
      ev.preventDefault();
      setError(errs.join(" "));
      return;
    }
    // Let the form post natively — register flow is one-shot,
    // and the server message includes the receipt confirmation.
  }

  // -----------------------------------------------------------
  // Bootstrap
  // -----------------------------------------------------------
  document.addEventListener("DOMContentLoaded", function () {
    document.documentElement.classList.remove("no-js");

    var root = $(".root");
    if (root) root.dataset.palette = TWEAKS.palette;

    // Session id for header
    var sessionId = Math.random().toString(16).slice(2, 10).toUpperCase();

    // Backdrop
    var bg = $("#bg-canvas");
    var stopBg = function () {};
    if (bg) {
      if (TWEAKS.backdrop === "code_rain") {
        stopBg = startCodeRain(bg, {
          color: PALETTE.primary,
          density: TWEAKS.rain_density,
          speed: TWEAKS.rain_speed,
          style: TWEAKS.rain_style,
        });
      } else if (TWEAKS.backdrop === "ops_map") {
        stopBg = startAgencyMap(bg, {
          palette: PALETTE,
          intensity: TWEAKS.map_intensity,
          show_radar: TWEAKS.show_radar,
          show_nodes: TWEAKS.show_nodes,
        });
      }
      // else: plain — leave canvas blank.
    }

    // Effects
    var scan = $(".scanlines");
    if (scan && !TWEAKS.scanlines) scan.remove();
    var vig = $(".vignette");
    if (vig && !TWEAKS.vignette) vig.remove();
    var lr = $(".rail-left"), rr = $(".rail-right");
    if (!TWEAKS.show_rails) {
      if (lr) lr.remove();
      if (rr) rr.remove();
    } else {
      startRail(lr);
      startRail(rr);
    }

    // Strips
    startHeader($(".strip"), sessionId);

    // Stage refs
    stages.boot        = $("#stage-boot");
    stages.login       = $("#stage-login");
    stages.authing     = $("#stage-authing");
    stages.granted     = $("#stage-granted");
    stages.denied      = $("#stage-denied");
    stages.requestForm = $("#stage-register");

    // Hide all then run boot
    Object.keys(stages).forEach(function (k) {
      if (stages[k]) stages[k].hidden = true;
    });

    // Primary mode
    if (CONFIG.mode === "register") {
      // Skip boot, jump straight to register.
      showStage("requestForm");
      var rform = $("#register-form");
      if (rform) rform.addEventListener("submit", function (ev) { submitRegister(rform, ev); });
    } else {
      // Boot -> login
      stages.boot.hidden = false;
      runBoot(function () {
        showStage("login");
        startSidePanel();
        // Subtitle typewriter
        var sub = $("#login-sub");
        if (sub) typewriter(sub, "CLEARANCE VERIFICATION REQUIRED ▮ DO NOT SHARE THIS TERMINAL ▮", 14);
        var form = $("#login-form");
        if (form) form.addEventListener("submit", function (ev) { submitLogin(form, ev); });
        // Retry / return-to-gate buttons
        var retry = $("#denied-retry");
        if (retry) retry.addEventListener("click", function () {
          setError(null);
          showStage("login");
        });
      });
    }

    // Register link wiring (already navigates via <a href> for no-JS)
  });
})();

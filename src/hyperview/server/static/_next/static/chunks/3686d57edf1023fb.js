(globalThis.TURBOPACK||(globalThis.TURBOPACK=[])).push(["object"==typeof document?document.currentScript:void 0,54214,e=>{"use strict";function t(e,t,i){if(t.length%2!=0)throw Error(`positions length must be even (got ${t.length})`);let r=t.length/2,o=i??new Uint16Array(r);if(o.length!==r)throw Error(`labels length must equal number of points (${r}), got ${o.length}`);return{n:r,positions:t,labels:o,geometry:e}}function i(e){let t=new Float32Array(2*e.length);for(let i=0;i<e.length;i++){let r=e[i];t[2*i]=r[0],t[2*i+1]=r[1]}return t}function r(e,t){if(e.length!==t.length)throw Error(`x/y length mismatch: ${e.length} vs ${t.length}`);let i=new Float32Array(2*e.length);for(let r=0;r<e.length;r++)i[2*r]=e[r],i[2*r+1]=t[r];return i}function o(e){let t=new Uint16Array(e.length);for(let i=0;i<e.length;i++){let r=e[i];if(!Number.isFinite(r)||r<0||r>65535)throw Error(`label index out of range at ${i}: ${r}`);t[i]=r}return t}e.s(["createDataset",()=>t,"packPositions",()=>i,"packPositionsXY",()=>r,"packUint16Labels",()=>o],15454),e.i(15454);let s=["#4e79a7","#f28e2c","#e15759","#76b7b2","#59a14f","#edc949","#af7aa1","#ff9da7","#9c755f","#bab0ab"],a="#ff0000",n="#ffffff";function l(e,t){return{kind:"indices",indices:e,computeTimeMs:t,has:t=>e.has(t)}}function h(e,t,i,r){return{kind:"geometry",geometry:e,computeTimeMs:i,has:i=>r(t[2*i],t[2*i+1],e.coords)}}function u(e,t,i,r,o){let s=.4*Math.min(r,o)*i.zoom;return{x:r/2+(e-i.centerX)*s,y:o/2-(t-i.centerY)*s}}function d(e,t,i,r,o){let s=.4*Math.min(r,o)*i.zoom;return{x:i.centerX+(e-r/2)/s,y:i.centerY-(t-o/2)/s}}function f(){return{type:"poincare",ax:0,ay:0,displayZoom:1}}function c(e,t,i,r){let o=e-i,s=t-r,a=1-(i*e+r*t),n=-(i*t-r*e),l=a*a+n*n;if(l<1e-12){let e=Math.sqrt(o*o+s*s);return e<1e-12?{x:0,y:0}:{x:o/e*.999,y:s/e*.999}}let h=(o*a+s*n)/l,u=(s*a-o*n)/l,d=h*h+u*u;if(d>=1){let e=Math.sqrt(d);return{x:h/e*.999,y:u/e*.999}}return{x:h,y:u}}function p(e,t,i,r){let o=e+i,s=t+r,a=1+(i*e+r*t),n=i*t-r*e,l=a*a+n*n;if(l<1e-12){let e=Math.sqrt(o*o+s*s);return e<1e-12?{x:0,y:0}:{x:o/e*.999,y:s/e*.999}}let h=(o*a+s*n)/l,u=(s*a-o*n)/l,d=h*h+u*u;if(d>=1){let e=Math.sqrt(d);return{x:h/e*.999,y:u/e*.999}}return{x:h,y:u}}function m(e,t,i,r,o){let s=.45*Math.min(r,o)*i.displayZoom,a=(e-r/2)/s,n=-(t-o/2)/s,l=a*a+n*n;if(l>=1){let e=Math.sqrt(l);return p(a/e*.999,n/e*.999,i.ax,i.ay)}return p(a,n,i.ax,i.ay)}function x(e,t,i,r,o,s,a){let n=.45*Math.min(s,a)*e.displayZoom,l=(e,t,i=.95)=>{let r=e*e+t*t;if(r>i*i){let o=Math.sqrt(r);return{x:e/o*i,y:t/o*i}}return{x:e,y:t}},h=l((t-s/2)/n,-(i-a/2)/n),u=l((r-s/2)/n,-(o-a/2)/n),d=p(h.x,h.y,e.ax,e.ay),f=function(e,t,i,r){let o=i*e-r*t,s=i*t+r*e,a=o*o+s*s-1;if(1e-10>Math.abs(a))return{x:-i,y:-r};let n=e-i,l=r-t,h=(-(1+o)*n+s*l)/a,u=((1-o)*l-s*n)/a,d=h*h+u*u;if(d>=1){let e=Math.sqrt(d);return{x:h/e*.99,y:u/e*.99}}return{x:h,y:u}}(d.x,d.y,u.x,u.y);return{...e,ax:f.x,ay:f.y}}function g(e,t,i){let r=i.length/2;if(r<3)return!1;let o=!1;for(let s=0,a=r-1;s<r;a=s++){let r=i[2*s],n=i[2*s+1],l=i[2*a],h=i[2*a+1];if(function(e,t,i,r,o,s,a){let n=Math.min(i,o)-1e-9,l=Math.max(i,o)+1e-9,h=Math.min(r,s)-1e-9,u=Math.max(r,s)+1e-9;if(e<n||e>l||t<h||t>u)return!1;let d=o-i,f=s-r,c=d*d+f*f;if(c<1e-9*1e-9)return 1e-9>=Math.sqrt((e-i)*(e-i)+(t-r)*(t-r));let p=Math.max(0,Math.min(1,((e-i)*d+(t-r)*f)/c)),m=i+p*d,x=r+p*f;return 1e-9>=Math.sqrt((e-m)*(e-m)+(t-x)*(t-x))}(e,t,r,n,l,h,1e-9))return!0;n>t!=h>t&&e<(l-r)*(t-n)/(h-n)+r&&(o=!o)}return o}function b(e){let t=1/0,i=1/0,r=-1/0,o=-1/0;for(let s=0;s<e.length;s+=2){let a=e[s],n=e[s+1];a<t&&(t=a),a>r&&(r=a),n<i&&(i=n),n>o&&(o=n)}return Number.isFinite(t)&&Number.isFinite(i)&&Number.isFinite(r)&&Number.isFinite(o)?{xMin:t,yMin:i,xMax:r,yMax:o}:{xMin:0,yMin:0,xMax:0,yMax:0}}function E(e,t,i){return e<t?t:e>i?i:0|e}class R{n;bounds;cellsX;cellsY;cellSizeX;cellSizeY;offsets;ids;constructor(e,t,i=64){this.n=e.length/2|0,this.bounds=t??function(e){let t=1/0,i=1/0,r=-1/0,o=-1/0;for(let s=0;s<e.length;s+=2){let a=e[s],n=e[s+1];a<t&&(t=a),a>r&&(r=a),n<i&&(i=n),n>o&&(o=n)}return Number.isFinite(t)&&Number.isFinite(i)?(1e-9>Math.abs(r-t)&&(r=t+1),1e-9>Math.abs(o-i)&&(o=i+1),{minX:t,minY:i,maxX:r,maxY:o}):{minX:0,minY:0,maxX:0,maxY:0}}(e);const r=this.bounds.maxX-this.bounds.minX,o=this.bounds.maxY-this.bounds.minY,s=Math.max(64,Math.min(1e6,Math.ceil(this.n/Math.max(1,i))));let a=Math.round(Math.sqrt(r/o*s)),n=Math.round(s/(a=E(a,8,2048)));n=E(n,8,2048),this.cellsX=a,this.cellsY=n,this.cellSizeX=r/a,this.cellSizeY=o/n;const l=a*n,h=new Uint32Array(l);for(let t=0;t<this.n;t++){const i=e[2*t],r=e[2*t+1],o=E(Math.floor((i-this.bounds.minX)/this.cellSizeX),0,a-1),s=E(Math.floor((r-this.bounds.minY)/this.cellSizeY),0,n-1);h[s*a+o]++}const u=new Uint32Array(l+1);let d=0;for(let e=0;e<l;e++)u[e]=d,d+=h[e];u[l]=d;const f=u.slice(0,l),c=new Uint32Array(this.n);for(let t=0;t<this.n;t++){const i=e[2*t],r=e[2*t+1],o=E(Math.floor((i-this.bounds.minX)/this.cellSizeX),0,a-1),s=E(Math.floor((r-this.bounds.minY)/this.cellSizeY),0,n-1)*a+o;c[f[s]++]=t}this.offsets=u,this.ids=c}forEachInAABB(e,t,i,r,o){e-=1e-12,t-=1e-12,i+=1e-12,r+=1e-12;let s=E(Math.floor((e-this.bounds.minX)/this.cellSizeX),0,this.cellsX-1),a=E(Math.floor((t-this.bounds.minY)/this.cellSizeY),0,this.cellsY-1),n=E(Math.floor((i-this.bounds.minX)/this.cellSizeX),0,this.cellsX-1),l=E(Math.floor((r-this.bounds.minY)/this.cellSizeY),0,this.cellsY-1);for(let e=a;e<=l;e++){let t=e*this.cellsX;for(let e=s;e<=n;e++){let i=t+e,r=this.offsets[i],s=this.offsets[i+1];for(let e=r;e<s;e++)o(this.ids[e])}}}queryRadius(e,t,i,r){r.length=0,this.forEachInAABB(e-i,t-i,e+i,t+i,e=>r.push(e))}}function T(e){let t=e.trim();if(!t.startsWith("#"))return[1,1,1,1];let i=t.slice(1);return 3===i.length?[parseInt(i[0]+i[0],16)/255,parseInt(i[1]+i[1],16)/255,parseInt(i[2]+i[2],16)/255,1]:6===i.length||8===i.length?[parseInt(i.slice(0,2),16)/255,parseInt(i.slice(2,4),16)/255,parseInt(i.slice(4,6),16)/255,8===i.length?parseInt(i.slice(6,8),16)/255:1]:[1,1,1,1]}function y(e,t,i){let r=e.createShader(t);if(!r)throw Error("Failed to create shader");if(e.shaderSource(r,i),e.compileShader(r),!e.getShaderParameter(r,e.COMPILE_STATUS)){let t=e.getShaderInfoLog(r)??"unknown";throw e.deleteShader(r),Error(`Shader compile failed: ${t}`)}return r}function _(e,t,i){let r=y(e,e.VERTEX_SHADER,t),o=y(e,e.FRAGMENT_SHADER,i),s=e.createProgram();if(!s)throw Error("Failed to create program");if(e.attachShader(s,r),e.attachShader(s,o),e.linkProgram(s),e.deleteShader(r),e.deleteShader(o),!e.getProgramParameter(s,e.LINK_STATUS)){let t=e.getProgramInfoLog(s)??"unknown";throw e.deleteProgram(s),Error(`Program link failed: ${t}`)}return s}function v(e,t,i,r){e.width=Math.max(1,Math.floor(t*r)),e.height=Math.max(1,Math.floor(i*r)),e.style.width=`${t}px`,e.style.height=`${i}px`}let A=`#version 300 es
precision highp float;
precision highp int;

flat in uint v_label;

// Present in the vertex stage too; redeclare here so we can compute AA width.
uniform float u_dpr;
uniform float u_pointRadiusCss;

uniform sampler2D u_paletteTex;
uniform int u_paletteSize;
uniform int u_paletteWidth;

out vec4 outColor;

void main() {
  vec2 p = gl_PointCoord * 2.0 - 1.0;
  // Anti-aliased circle: avoid harsh discard edges that can look like
  // "weird polygons" at small sizes or without MSAA.
  float r = length(p);
  // Ensure at least ~1px transition (in point-local coordinates) so small
  // points remain visually circular.
  float radiusPx = max(u_pointRadiusCss * u_dpr, 1.0);
  // Slightly wider than 1px helps circles stay round-looking when zoomed out
  // (where points are perceptually tiny and aliasing is more obvious).
  float aa = max(fwidth(r), 1.5 / radiusPx);
  float alpha = 1.0 - smoothstep(1.0 - aa, 1.0 + aa, r);
  if (alpha <= 0.0) discard;

  int size = max(u_paletteSize, 1);
  int w = max(u_paletteWidth, 1);
  int idx = int(v_label) % size;
  int x = idx % w;
  int y = idx / w;
  vec4 c = texelFetch(u_paletteTex, ivec2(x, y), 0);
  outColor = vec4(c.rgb, c.a * alpha);
}
`,S=`#version 300 es
precision highp float;
precision highp int;

flat in uint v_label;

uniform sampler2D u_paletteTex;
uniform int u_paletteSize;
uniform int u_paletteWidth;

out vec4 outColor;

void main() {
  int size = max(u_paletteSize, 1);
  int w = max(u_paletteWidth, 1);
  int idx = int(v_label) % size;
  int x = idx % w;
  int y = idx / w;
  outColor = texelFetch(u_paletteTex, ivec2(x, y), 0);
}
`,P=`#version 300 es
precision highp float;
precision highp int;

uniform float u_dpr;
uniform float u_pointRadiusCss;

uniform vec4 u_color;
uniform float u_pointSizePx;
uniform float u_ringThicknessPx;
uniform int u_ringMode; // 0 = solid, 1 = ring

out vec4 outColor;

void main() {
  vec2 p = gl_PointCoord * 2.0 - 1.0;
  float r = length(p);
  float radiusPx = max(u_pointRadiusCss * u_dpr, 1.0);
  float aa = max(fwidth(r), 1.5 / radiusPx);
  float outer = 1.0 - smoothstep(1.0 - aa, 1.0 + aa, r);
  if (outer <= 0.0) discard;

  float alpha = outer;

  if (u_ringMode == 1) {
    float radiusPx = u_pointSizePx * 0.5;
    float t = clamp(u_ringThicknessPx / max(radiusPx, 1e-6), 0.0, 1.0);
    float inner = 1.0 - t;
    // Keep only the outer ring with an anti-aliased inner boundary.
    float innerMask = smoothstep(inner - aa, inner + aa, r);
    alpha *= innerMask;
    if (alpha <= 0.0) discard;
  }

  outColor = vec4(u_color.rgb, u_color.a * alpha);
}
`,M=`#version 300 es
precision highp float;

out vec2 v_uv;

void main() {
  // Fullscreen triangle
  // (-1,-1), (3,-1), (-1,3)
  if (gl_VertexID == 0) {
    gl_Position = vec4(-1.0, -1.0, 0.0, 1.0);
    v_uv = vec2(0.0, 0.0);
  } else if (gl_VertexID == 1) {
    gl_Position = vec4(3.0, -1.0, 0.0, 1.0);
    v_uv = vec2(2.0, 0.0);
  } else {
    gl_Position = vec4(-1.0, 3.0, 0.0, 1.0);
    v_uv = vec2(0.0, 2.0);
  }
}
`,F=`#version 300 es
precision highp float;

in vec2 v_uv;

uniform sampler2D u_tex;

out vec4 outColor;

void main() {
  vec2 uv = clamp(v_uv, 0.0, 1.0);
  outColor = texture(u_tex, uv);
}
`,B=`#version 300 es
precision highp float;
precision highp int;

uniform vec2 u_cssSize;
uniform float u_dpr;
uniform float u_displayZoom;

uniform vec4 u_diskFillColor;
uniform vec4 u_diskBorderColor;
uniform vec4 u_gridColor;
uniform float u_diskBorderWidthPx;
uniform float u_gridWidthPx;

out vec4 outColor;

void main() {
  // Convert framebuffer pixels to CSS pixels
  vec2 fragCss = gl_FragCoord.xy / max(u_dpr, 1.0);
  vec2 center = u_cssSize * 0.5;

  float diskRadius = min(u_cssSize.x, u_cssSize.y) * 0.45 * u_displayZoom;
  vec2 p = fragCss - center;
  float dist = length(p);

  // Reference-like styling
  vec3 diskFill = u_diskFillColor.rgb;
  vec3 diskBorder = u_diskBorderColor.rgb;

  float borderWidth = max(u_diskBorderWidthPx, 0.0);
  float halfW = 0.5 * borderWidth;

  // Anti-aliasing width (CSS px). Keep at least 1px for crisp edges.
  float aa = max(1.0, fwidth(dist));

  // Discard outside disk+border region so the clear color remains intact.
  if (dist > diskRadius + halfW + aa) discard;

  // Outer fade for anti-aliased boundary
  float outerAlpha = 1.0 - smoothstep(diskRadius + halfW - aa, diskRadius + halfW + aa, dist);

  // Border mask
  float borderInner = smoothstep(diskRadius - halfW - aa, diskRadius - halfW + aa, dist);
  float borderOuter = 1.0 - smoothstep(diskRadius + halfW - aa, diskRadius + halfW + aa, dist);
  float borderMask = clamp(borderInner * borderOuter, 0.0, 1.0);

  vec3 col = mix(diskFill, diskBorder, borderMask);

  // ------------------------------------------------------------------------
  // Reference-like hyperbolic grid overlay
  // ------------------------------------------------------------------------
  // Matches HyperbolicReference.drawHyperbolicGrid():
  // - 8 radial lines (geodesics through origin)
  // - 5 concentric circles
  vec3 gridCol = u_gridColor.rgb;
  float gridWidth = max(u_gridWidthPx, 0.0);
  float halfGrid = 0.5 * gridWidth;

  // AA width for thin lines in CSS pixel space.
  float aaLine = max(1.0, fwidth(dist));

  float gridMask = 0.0;

  // Concentric circles (5)
  for (int i = 1; i <= 5; i++) {
    float r = (float(i) / 6.0) * diskRadius;
    float d = abs(dist - r);
    float m = 1.0 - smoothstep(halfGrid - aaLine, halfGrid + aaLine, d);
    gridMask = max(gridMask, m);
  }

  // Radial lines (8), angle = (i/8)*pi
  // Distance to line through origin with direction (cos a, sin a): |cross(p, dir)|
  for (int i = 0; i < 8; i++) {
    float a = (float(i) / 8.0) * 3.141592653589793;
    vec2 dir = vec2(cos(a), sin(a));
    float d = abs(p.x * dir.y - p.y * dir.x);
    float m = 1.0 - smoothstep(halfGrid - aaLine, halfGrid + aaLine, d);
    gridMask = max(gridMask, m);
  }

  // Apply grid on top of disk fill/border. Use u_gridColor alpha as intensity.
  col = mix(col, gridCol, clamp(gridMask, 0.0, 1.0) * clamp(u_gridColor.a, 0.0, 1.0));
  outColor = vec4(col, outerAlpha);
}
`,D=`#version 300 es
precision highp float;
precision highp int;

layout(location = 0) in vec2 a_pos;
layout(location = 1) in uint a_label;

uniform vec2 u_center;
uniform vec2 u_cssSize;
uniform float u_zoom;
uniform float u_dpr;
uniform float u_pointRadiusCss;

flat out uint v_label;

void main() {
  float baseScale = min(u_cssSize.x, u_cssSize.y) * 0.4 * u_zoom;
  float sx = u_cssSize.x * 0.5 + (a_pos.x - u_center.x) * baseScale;
  float sy = u_cssSize.y * 0.5 - (a_pos.y - u_center.y) * baseScale;

  vec2 dbufSize = u_cssSize * u_dpr;
  vec2 dbuf = vec2(sx, sy) * u_dpr;

  float cx = (dbuf.x / dbufSize.x) * 2.0 - 1.0;
  float cy = 1.0 - (dbuf.y / dbufSize.y) * 2.0;

  gl_Position = vec4(cx, cy, 0.0, 1.0);
  gl_PointSize = (u_pointRadiusCss * 2.0) * u_dpr;
  v_label = a_label;
}
`,C=`#version 300 es
precision highp float;
precision highp int;

layout(location = 0) in vec2 a_pos;
layout(location = 1) in uint a_label;

uniform vec2 u_cssSize;
uniform float u_dpr;
uniform float u_pointRadiusCss;

uniform vec2 u_a;            // camera translation (ax, ay)
uniform float u_displayZoom; // visual zoom

flat out uint v_label;

vec2 mobiusTransform(vec2 z, vec2 a) {
  // (z - a) / (1 - conj(a) * z)
  vec2 num = z - a;

  // denom = 1 - (ax*zx + ay*zy)  + i * (-(ax*zy - ay*zx))
  float denomX = 1.0 - (a.x * z.x + a.y * z.y);
  float denomY = -(a.x * z.y - a.y * z.x);
  float denomNormSq = denomX * denomX + denomY * denomY;
  if (denomNormSq < 1e-12) {
    // Push outside clip
    return vec2(2.0, 2.0);
  }

  // complex division
  float rx = (num.x * denomX + num.y * denomY) / denomNormSq;
  float ry = (num.y * denomX - num.x * denomY) / denomNormSq;
  return vec2(rx, ry);
}

void main() {
  vec2 w = mobiusTransform(a_pos, u_a);
  float r2 = dot(w, w);
  if (r2 >= 1.0) {
    gl_Position = vec4(2.0, 2.0, 0.0, 1.0);
    gl_PointSize = 0.0;
    v_label = a_label;
    return;
  }

  float diskRadius = min(u_cssSize.x, u_cssSize.y) * 0.45 * u_displayZoom;
  float sx = u_cssSize.x * 0.5 + w.x * diskRadius;
  float sy = u_cssSize.y * 0.5 - w.y * diskRadius;

  vec2 dbufSize = u_cssSize * u_dpr;
  vec2 dbuf = vec2(sx, sy) * u_dpr;

  float cx = (dbuf.x / dbufSize.x) * 2.0 - 1.0;
  float cy = 1.0 - (dbuf.y / dbufSize.y) * 2.0;

  gl_Position = vec4(cx, cy, 0.0, 1.0);
  gl_PointSize = (u_pointRadiusCss * 2.0) * u_dpr;
  v_label = a_label;
}
`;class U{canvas=null;width=0;height=0;deviceDpr=1;canvasDpr=1;dpr=1;dataset=null;selection=new Set;hoveredIndex=-1;pointRadiusCss=3;colors=s;backgroundColor="#0a0a0a";poincareDiskFillColor="#141414";poincareDiskBorderColor="#666666";poincareGridColor="#66666633";poincareDiskBorderWidthPx=2;poincareGridWidthPx=.5;paletteSize=0;paletteDirty=!0;paletteTex=null;paletteTexW=0;paletteTexH=0;paletteBytes=new Uint8Array(0);paletteTexUnit=1;scratchIds=[];hoverPosScratch=new Float32Array(2);hoverLabScratch=new Uint16Array(1);hoverIndexScratch=new Uint32Array(1);lastViewChangeTs=0;markViewChanged(){this.lastViewChangeTs=performance.now()}endInteraction(){this.lastViewChangeTs=0}markBackdropDirty(){this.backdropDirty=!0}uploadPoincareDiskStyleUniforms(){let e=this.gl,t=this.poincareDisk;if(!e||!t)return;let i=T(this.poincareDiskFillColor),r=T(this.poincareDiskBorderColor),o=T(this.poincareGridColor);t.uDiskFillColor&&e.uniform4f(t.uDiskFillColor,i[0],i[1],i[2],i[3]),t.uDiskBorderColor&&e.uniform4f(t.uDiskBorderColor,r[0],r[1],r[2],r[3]),t.uGridColor&&e.uniform4f(t.uGridColor,o[0],o[1],o[2],o[3]),t.uDiskBorderWidthPx&&e.uniform1f(t.uDiskBorderWidthPx,this.poincareDiskBorderWidthPx),t.uGridWidthPx&&e.uniform1f(t.uGridWidthPx,this.poincareGridWidthPx)}getBackdropZoom(){return 1}dataIndex=null;gl=null;vao=null;posBuffer=null;labelBuffer=null;hoverVao=null;hoverPosBuffer=null;hoverLabelBuffer=null;selectionVao=null;selectionPosBuffer=null;selectionLabelBuffer=null;selectionOverlayCount=0;selectionEbo=null;hoverEbo=null;interactionEbo=null;interactionCount=0;maxBaseDrawPoints=4e6;maxGpuUploadPoints=1e7;gpuUsesFullDataset=!0;gpuPointCount=0;policy={fragmentBudget:1e8,circleBudget:6e7,squareOnRatio:1,squareOffRatio:.75,minPointsDpr:.35};renderAsSquares=!1;__debugPolicy=null;backdropTex=null;backdropFbo=null;backdropW=0;backdropH=0;backdropDpr=1;backdropZoom=NaN;backdropDirty=!0;pointsTex=null;pointsFbo=null;pointsW=0;pointsH=0;programComposite=null;uCompositeTex=null;poincareDisk=null;pointsCircle=null;pointsSquare=null;programSolid=null;uSolidColor=null;uSolidPointSizePx=null;uSolidRingThicknessPx=null;uSolidRingMode=null;uCssSizeSolid=null;uDprSolid=null;uPointRadiusSolid=null;selectionDirty=!0;hoverDirty=!0;init(e,t){this.canvas=e,this.width=t.width,this.height=t.height,this.deviceDpr=t.devicePixelRatio??window.devicePixelRatio??1,this.canvasDpr=this.deviceDpr,this.dpr=this.deviceDpr;let i="string"==typeof t.poincareDiskFillColor;t.backgroundColor&&(this.backgroundColor=t.backgroundColor),t.pointRadius&&(this.pointRadiusCss=t.pointRadius),t.colors&&(this.colors=t.colors),this.poincareDiskFillColor=i?t.poincareDiskFillColor:this.poincareDiskFillColor,t.poincareDiskBorderColor&&(this.poincareDiskBorderColor=t.poincareDiskBorderColor),t.poincareGridColor&&(this.poincareGridColor=t.poincareGridColor),"number"==typeof t.poincareDiskBorderWidthPx&&Number.isFinite(t.poincareDiskBorderWidthPx)&&(this.poincareDiskBorderWidthPx=Math.max(0,t.poincareDiskBorderWidthPx)),"number"==typeof t.poincareGridWidthPx&&Number.isFinite(t.poincareGridWidthPx)&&(this.poincareGridWidthPx=Math.max(0,t.poincareGridWidthPx)),this.paletteDirty=!0}chooseRenderDpr(e){let t=this.deviceDpr,i=Math.max(1,this.width)*Math.max(1,this.height),r=e>this.maxBaseDrawPoints?this.estimateSubsampleCount(e):e,o=Math.sqrt((e>=1e6?i>1e6?2e5:5e5:e>=5e5?14e5:e>=25e4?21e5:8e6)/i),s=Math.max(.5,this.pointRadiusCss),a=Math.max(1,r)*Math.PI*s*s,n=Math.sqrt(this.policy.fragmentBudget/a),l=e>=1e6?1:e>=5e5?1.25:1.5;return Math.max(e>=1e6?this.policy.minPointsDpr:e>=5e5?.75:1,Math.min(t,l,o,n))}estimateSubsampleCount(e){if(e<5e5)return e;let t=Math.min(e,Math.max(25e4,Math.min(this.maxBaseDrawPoints,Math.floor(.25*e)))),i=Math.max(1,Math.floor(e/t));return Math.min(t,Math.ceil(e/i))}estimatePointFragments(e,t){let i=Math.max(.5,this.pointRadiusCss),r=Math.max(0,t);return Math.max(0,e)*Math.PI*i*i*r*r}updateSquarePointPolicy(e){let t=this.policy.circleBudget*this.policy.squareOnRatio,i=this.policy.circleBudget*this.policy.squareOffRatio;if(this.dpr<=.75){this.renderAsSquares=!0;return}this.renderAsSquares?e<=i&&(this.renderAsSquares=!1):e>=t&&(this.renderAsSquares=!0)}setDataset(e){this.dataset=e,this.selection=new Set,this.hoveredIndex=-1,this.selectionDirty=!0,this.hoverDirty=!0;let t=this.chooseRenderDpr(e.n);t!==this.dpr&&(this.dpr=t),this.dataIndex=new R(e.positions,void 0,64),this.gl&&this.uploadDatasetToGPU(),this.markBackdropDirty()}resize(e,t){this.width=e,this.height=t,this.gl&&this.canvas&&(v(this.canvas,e,t,this.canvasDpr),this.gl.viewport(0,0,this.canvas.width,this.canvas.height),this.markBackdropDirty())}setSelection(e){let t=e.size;this.selection=t<=2e5?new Set(e):e,this.selectionDirty=!0,this.gl&&this.uploadSelectionToGPU()}getSelection(){return this.selection.size<=2e5?new Set(this.selection):this.selection}setHovered(e){this.hoveredIndex=e,this.hoverDirty=!0,this.gl&&this.uploadHoverToGPU()}destroy(){let e=this.gl;e&&(this.pointsCircle&&e.deleteProgram(this.pointsCircle.program),this.pointsSquare&&e.deleteProgram(this.pointsSquare.program),this.programSolid&&e.deleteProgram(this.programSolid),this.poincareDisk&&e.deleteProgram(this.poincareDisk.program),this.vao&&e.deleteVertexArray(this.vao),this.hoverVao&&e.deleteVertexArray(this.hoverVao),this.selectionVao&&e.deleteVertexArray(this.selectionVao),this.posBuffer&&e.deleteBuffer(this.posBuffer),this.labelBuffer&&e.deleteBuffer(this.labelBuffer),this.hoverPosBuffer&&e.deleteBuffer(this.hoverPosBuffer),this.hoverLabelBuffer&&e.deleteBuffer(this.hoverLabelBuffer),this.selectionPosBuffer&&e.deleteBuffer(this.selectionPosBuffer),this.selectionLabelBuffer&&e.deleteBuffer(this.selectionLabelBuffer),this.selectionEbo&&e.deleteBuffer(this.selectionEbo),this.hoverEbo&&e.deleteBuffer(this.hoverEbo),this.interactionEbo&&e.deleteBuffer(this.interactionEbo),this.backdropFbo&&e.deleteFramebuffer(this.backdropFbo),this.backdropTex&&e.deleteTexture(this.backdropTex),this.pointsFbo&&e.deleteFramebuffer(this.pointsFbo),this.pointsTex&&e.deleteTexture(this.pointsTex),this.paletteTex&&e.deleteTexture(this.paletteTex),this.programComposite&&e.deleteProgram(this.programComposite)),this.gl=null,this.vao=null,this.hoverVao=null,this.selectionVao=null,this.posBuffer=null,this.labelBuffer=null,this.hoverPosBuffer=null,this.hoverLabelBuffer=null,this.selectionPosBuffer=null,this.selectionLabelBuffer=null,this.selectionOverlayCount=0,this.selectionEbo=null,this.hoverEbo=null,this.interactionEbo=null,this.interactionCount=0,this.gpuUsesFullDataset=!0,this.gpuPointCount=0,this.backdropFbo=null,this.backdropTex=null,this.backdropW=0,this.backdropH=0,this.backdropDpr=1,this.backdropZoom=NaN,this.backdropDirty=!0,this.pointsFbo=null,this.pointsTex=null,this.pointsW=0,this.pointsH=0,this.programComposite=null,this.uCompositeTex=null,this.pointsCircle=null,this.pointsSquare=null,this.programSolid=null,this.poincareDisk=null,this.paletteTex=null,this.paletteTexW=0,this.paletteTexH=0,this.paletteSize=0,this.paletteDirty=!0}uploadPaletteUniforms(){let e=this.gl;if(!e)return;let t=this.colors.length,i=Math.max(1,Math.min(t,65536)),r=e.getParameter(e.MAX_TEXTURE_SIZE),o=Math.min(r,i),s=Math.ceil(i/o);if(s>r)throw Error(`Palette too large for WebGL texture: size=${i}, maxTex=${r}`);let a=o*s;if(this.paletteBytes.length!==4*a?this.paletteBytes=new Uint8Array(4*a):this.paletteBytes.fill(0),0===t)this.paletteBytes[0]=255,this.paletteBytes[1]=255,this.paletteBytes[2]=255,this.paletteBytes[3]=255;else for(let e=0;e<i;e++){let[t,i,r,o]=function(e){let t=e.trim();if(!t.startsWith("#"))return[255,255,255,255];let i=t.slice(1);return 3===i.length?[parseInt(i[0]+i[0],16),parseInt(i[1]+i[1],16),parseInt(i[2]+i[2],16),255]:6===i.length||8===i.length?[parseInt(i.slice(0,2),16),parseInt(i.slice(2,4),16),parseInt(i.slice(4,6),16),8===i.length?parseInt(i.slice(6,8),16):255]:[255,255,255,255]}(this.colors[e]),s=4*e;this.paletteBytes[s+0]=t,this.paletteBytes[s+1]=i,this.paletteBytes[s+2]=r,this.paletteBytes[s+3]=o}if(!this.paletteTex){if(this.paletteTex=e.createTexture(),!this.paletteTex)throw Error("Failed to create palette texture");e.activeTexture(e.TEXTURE0+this.paletteTexUnit),e.bindTexture(e.TEXTURE_2D,this.paletteTex),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_MIN_FILTER,e.NEAREST),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_MAG_FILTER,e.NEAREST),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_WRAP_S,e.CLAMP_TO_EDGE),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_WRAP_T,e.CLAMP_TO_EDGE),e.bindTexture(e.TEXTURE_2D,null),e.activeTexture(e.TEXTURE0)}this.paletteSize=i,this.paletteTexW=o,this.paletteTexH=s,e.activeTexture(e.TEXTURE0+this.paletteTexUnit),e.bindTexture(e.TEXTURE_2D,this.paletteTex),e.pixelStorei(e.UNPACK_ALIGNMENT,1),e.texImage2D(e.TEXTURE_2D,0,e.RGBA8,o,s,0,e.RGBA,e.UNSIGNED_BYTE,this.paletteBytes),e.bindTexture(e.TEXTURE_2D,null),e.activeTexture(e.TEXTURE0);let n=t=>{t&&(e.useProgram(t.program),t.uPaletteTex&&e.uniform1i(t.uPaletteTex,this.paletteTexUnit),t.uPaletteSize&&e.uniform1i(t.uPaletteSize,this.paletteSize),t.uPaletteWidth&&e.uniform1i(t.uPaletteWidth,this.paletteTexW))};n(this.pointsCircle),n(this.pointsSquare),this.paletteDirty=!1}bindPaletteTexture(){let e=this.gl;e&&this.paletteTex&&(e.activeTexture(e.TEXTURE0+this.paletteTexUnit),e.bindTexture(e.TEXTURE_2D,this.paletteTex),e.activeTexture(e.TEXTURE0))}async countSelection(e,t={}){let i=this.dataset,r=this.dataIndex;if(!i||!r)return 0;if(e.indices)return e.indices.size;if("geometry"!==e.kind||!e.geometry)return 0;let o=e.geometry.coords;if(o.length/2<3)return 0;let s=e.geometry.bounds;if(!s){let e=1/0,t=1/0,i=-1/0,r=-1/0;for(let s=0;s<o.length;s+=2){let a=o[s],n=o[s+1];a<e&&(e=a),a>i&&(i=a),n<t&&(t=n),n>r&&(r=n)}s={xMin:e,yMin:t,xMax:i,yMax:r}}let a=t.shouldCancel,n=t.onProgress,l="number"==typeof t.yieldEveryMs&&Number.isFinite(t.yieldEveryMs)?Math.max(0,t.yieldEveryMs):8,h=s.xMin-1e-12,u=s.yMin-1e-12,d=s.xMax+1e-12,f=s.yMax+1e-12,c=(e,t,i)=>e<t?t:e>i?i:0|e,p=c(Math.floor((h-r.bounds.minX)/r.cellSizeX),0,r.cellsX-1),m=c(Math.floor((u-r.bounds.minY)/r.cellSizeY),0,r.cellsY-1),x=c(Math.floor((d-r.bounds.minX)/r.cellSizeX),0,r.cellsX-1),b=c(Math.floor((f-r.bounds.minY)/r.cellSizeY),0,r.cellsY-1),E=i.positions,R=r.ids,T=r.offsets,y=0,_=0,v=16384,A=l>0?performance.now():0;for(let e=m;e<=b;e++){let t=e*r.cellsX;for(let e=p;e<=x;e++){let i=t+e,r=T[i],h=T[i+1];for(let e=r;e<h;e++){let t=R[e],i=E[2*t],r=E[2*t+1];if(!(i<s.xMin)&&!(i>s.xMax)&&!(r<s.yMin)&&!(r>s.yMax)&&(g(i,r,o)&&y++,_++,l>0&&_>=v)){if(v=_+16384,a?.())return y;performance.now()-A>=l&&(n?.(y,_),await new Promise(e=>requestAnimationFrame(()=>e())),A=performance.now())}}}}return n?.(y,_),y}ensureGL(){if(this.gl)return;if(!this.canvas)throw Error("Renderer not initialized");v(this.canvas,this.width,this.height,this.canvasDpr);let e=this.canvas.getContext("webgl2",{antialias:!1,alpha:!1,depth:!1,stencil:!1,preserveDrawingBuffer:!1,premultipliedAlpha:!1,desynchronized:!0});if(!e)throw Error("Failed to get WebGL2 context (is the canvas already using 2D context?)");this.gl=e,e.disable(e.DEPTH_TEST),e.disable(e.CULL_FACE),e.enable(e.BLEND),e.blendFunc(e.SRC_ALPHA,e.ONE_MINUS_SRC_ALPHA);let[t,i,r,o]=T(this.backgroundColor);e.clearColor(t,i,r,o),e.viewport(0,0,this.canvas.width,this.canvas.height),this.createProgramsAndBuffers(),this.uploadPaletteUniforms(),this.dataset&&this.uploadDatasetToGPU(),this.uploadSelectionToGPU(),this.uploadHoverToGPU(),this.markBackdropDirty()}ensurePointsResources(){if(!this.gl||!this.canvas)return;let e=this.gl,t=Math.max(1,Math.floor(this.width*this.dpr)),i=Math.max(1,Math.floor(this.height*this.dpr)),r=e.getParameter(e.MAX_TEXTURE_SIZE);if(t>r||i>r){let e=Math.min(1,r/t,r/i);t=Math.max(1,Math.floor(t*e)),i=Math.max(1,Math.floor(i*e))}if(!this.pointsTex){if(this.pointsTex=e.createTexture(),!this.pointsTex)throw Error("Failed to create points texture");e.bindTexture(e.TEXTURE_2D,this.pointsTex),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_MIN_FILTER,e.LINEAR),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_MAG_FILTER,e.LINEAR),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_WRAP_S,e.CLAMP_TO_EDGE),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_WRAP_T,e.CLAMP_TO_EDGE),e.bindTexture(e.TEXTURE_2D,null)}if(!this.pointsFbo&&(this.pointsFbo=e.createFramebuffer(),!this.pointsFbo))throw Error("Failed to create points framebuffer");if(t!==this.pointsW||i!==this.pointsH){this.pointsW=t,this.pointsH=i,e.bindTexture(e.TEXTURE_2D,this.pointsTex),e.texImage2D(e.TEXTURE_2D,0,e.RGBA,t,i,0,e.RGBA,e.UNSIGNED_BYTE,null),e.bindTexture(e.TEXTURE_2D,null),e.bindFramebuffer(e.FRAMEBUFFER,this.pointsFbo),e.framebufferTexture2D(e.FRAMEBUFFER,e.COLOR_ATTACHMENT0,e.TEXTURE_2D,this.pointsTex,0);let r=e.checkFramebufferStatus(e.FRAMEBUFFER);if(e.bindFramebuffer(e.FRAMEBUFFER,null),r!==e.FRAMEBUFFER_COMPLETE)throw Error(`Points framebuffer incomplete: ${r}`)}}ensureBackdropResources(){if(!this.gl||!this.canvas||"poincare"!==this.geometryKind()||!this.poincareDisk||!this.vao)return;let e=this.gl,t=Math.max(1,this.canvasDpr),i=Math.max(1,Math.floor(this.width*t)),r=Math.max(1,Math.floor(this.height*t)),o=e.getParameter(e.MAX_TEXTURE_SIZE);if(i>o||r>o){let e=Math.min(1,o/i,o/r);i=Math.max(1,Math.floor(i*e)),r=Math.max(1,Math.floor(r*e)),this.backdropDpr=t*e}else this.backdropDpr=t;if(!this.backdropTex){if(this.backdropTex=e.createTexture(),!this.backdropTex)throw Error("Failed to create backdrop texture");e.bindTexture(e.TEXTURE_2D,this.backdropTex),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_MIN_FILTER,e.NEAREST),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_MAG_FILTER,e.NEAREST),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_WRAP_S,e.CLAMP_TO_EDGE),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_WRAP_T,e.CLAMP_TO_EDGE),e.bindTexture(e.TEXTURE_2D,null)}if(!this.backdropFbo&&(this.backdropFbo=e.createFramebuffer(),!this.backdropFbo))throw Error("Failed to create backdrop framebuffer");if(i!==this.backdropW||r!==this.backdropH){this.backdropW=i,this.backdropH=r,e.bindTexture(e.TEXTURE_2D,this.backdropTex),e.texImage2D(e.TEXTURE_2D,0,e.RGBA,i,r,0,e.RGBA,e.UNSIGNED_BYTE,null),e.bindTexture(e.TEXTURE_2D,null),e.bindFramebuffer(e.FRAMEBUFFER,this.backdropFbo),e.framebufferTexture2D(e.FRAMEBUFFER,e.COLOR_ATTACHMENT0,e.TEXTURE_2D,this.backdropTex,0);let t=e.checkFramebufferStatus(e.FRAMEBUFFER);if(e.bindFramebuffer(e.FRAMEBUFFER,null),t!==e.FRAMEBUFFER_COMPLETE)throw Error(`Backdrop framebuffer incomplete: ${t}`);this.markBackdropDirty()}}renderBackdropIfNeeded(){if(!this.gl||!this.canvas||"poincare"!==this.geometryKind()||!this.poincareDisk||!this.vao||(this.ensureBackdropResources(),!this.backdropFbo))return;let e=this.getBackdropZoom(),t=Number.isFinite(this.backdropZoom)&&1e-12>=Math.abs(this.backdropZoom-e);if(!this.backdropDirty&&t)return;let i=this.gl;i.bindFramebuffer(i.FRAMEBUFFER,this.backdropFbo),i.viewport(0,0,this.backdropW,this.backdropH);let[r,o,s,a]=T(this.backgroundColor);i.clearColor(r,o,s,a),i.clear(i.COLOR_BUFFER_BIT),i.useProgram(this.poincareDisk.program),this.bindViewUniformsForProgram(this.poincareDisk.program),this.uploadPoincareDiskStyleUniforms(),this.poincareDisk.uCssSize&&i.uniform2f(this.poincareDisk.uCssSize,this.width,this.height),this.poincareDisk.uDpr&&i.uniform1f(this.poincareDisk.uDpr,this.backdropDpr),i.bindVertexArray(this.vao),i.drawArrays(i.TRIANGLES,0,3),i.bindFramebuffer(i.FRAMEBUFFER,null),i.viewport(0,0,this.canvas.width,this.canvas.height),this.backdropZoom=e,this.backdropDirty=!1}createProgramsAndBuffers(){let e=this.gl,t="euclidean"===this.geometryKind()?D:C,i=_(e,t,A),r=_(e,t,S);if(this.programSolid=_(e,t,P),this.programComposite=_(e,M,F),e.useProgram(this.programComposite),this.uCompositeTex=e.getUniformLocation(this.programComposite,"u_tex"),"poincare"===this.geometryKind()){let t=_(e,M,B);this.poincareDisk={program:t,uCssSize:e.getUniformLocation(t,"u_cssSize"),uDpr:e.getUniformLocation(t,"u_dpr"),uDiskFillColor:e.getUniformLocation(t,"u_diskFillColor"),uDiskBorderColor:e.getUniformLocation(t,"u_diskBorderColor"),uGridColor:e.getUniformLocation(t,"u_gridColor"),uDiskBorderWidthPx:e.getUniformLocation(t,"u_diskBorderWidthPx"),uGridWidthPx:e.getUniformLocation(t,"u_gridWidthPx")},e.useProgram(t),this.uploadPoincareDiskStyleUniforms()}if(e.useProgram(i),this.pointsCircle={program:i,uPaletteTex:e.getUniformLocation(i,"u_paletteTex"),uPaletteSize:e.getUniformLocation(i,"u_paletteSize"),uPaletteWidth:e.getUniformLocation(i,"u_paletteWidth"),uCssSize:e.getUniformLocation(i,"u_cssSize"),uDpr:e.getUniformLocation(i,"u_dpr"),uPointRadius:e.getUniformLocation(i,"u_pointRadiusCss")},e.useProgram(r),this.pointsSquare={program:r,uPaletteTex:e.getUniformLocation(r,"u_paletteTex"),uPaletteSize:e.getUniformLocation(r,"u_paletteSize"),uPaletteWidth:e.getUniformLocation(r,"u_paletteWidth"),uCssSize:e.getUniformLocation(r,"u_cssSize"),uDpr:e.getUniformLocation(r,"u_dpr"),uPointRadius:e.getUniformLocation(r,"u_pointRadiusCss")},e.useProgram(this.programSolid),this.uSolidColor=e.getUniformLocation(this.programSolid,"u_color"),this.uSolidPointSizePx=e.getUniformLocation(this.programSolid,"u_pointSizePx"),this.uSolidRingThicknessPx=e.getUniformLocation(this.programSolid,"u_ringThicknessPx"),this.uSolidRingMode=e.getUniformLocation(this.programSolid,"u_ringMode"),this.uCssSizeSolid=e.getUniformLocation(this.programSolid,"u_cssSize"),this.uDprSolid=e.getUniformLocation(this.programSolid,"u_dpr"),this.uPointRadiusSolid=e.getUniformLocation(this.programSolid,"u_pointRadiusCss"),this.vao=e.createVertexArray(),this.posBuffer=e.createBuffer(),this.labelBuffer=e.createBuffer(),this.hoverVao=e.createVertexArray(),this.hoverPosBuffer=e.createBuffer(),this.hoverLabelBuffer=e.createBuffer(),this.selectionVao=e.createVertexArray(),this.selectionPosBuffer=e.createBuffer(),this.selectionLabelBuffer=e.createBuffer(),this.selectionEbo=e.createBuffer(),this.hoverEbo=e.createBuffer(),this.interactionEbo=e.createBuffer(),!this.vao||!this.posBuffer||!this.labelBuffer||!this.hoverVao||!this.hoverPosBuffer||!this.hoverLabelBuffer||!this.selectionVao||!this.selectionPosBuffer||!this.selectionLabelBuffer||!this.selectionEbo||!this.hoverEbo||!this.interactionEbo)throw Error("Failed to allocate WebGL resources");e.bindVertexArray(this.vao),e.bindBuffer(e.ARRAY_BUFFER,this.posBuffer),e.enableVertexAttribArray(0),e.vertexAttribPointer(0,2,e.FLOAT,!1,0,0),e.bindBuffer(e.ARRAY_BUFFER,this.labelBuffer),e.enableVertexAttribArray(1),e.vertexAttribIPointer(1,1,e.UNSIGNED_SHORT,0,0),e.bindVertexArray(null),e.bindBuffer(e.ARRAY_BUFFER,null),e.bindVertexArray(this.hoverVao),e.bindBuffer(e.ARRAY_BUFFER,this.hoverPosBuffer),e.enableVertexAttribArray(0),e.vertexAttribPointer(0,2,e.FLOAT,!1,0,0),e.bindBuffer(e.ARRAY_BUFFER,this.hoverLabelBuffer),e.enableVertexAttribArray(1),e.vertexAttribIPointer(1,1,e.UNSIGNED_SHORT,0,0),e.bindVertexArray(null),e.bindBuffer(e.ARRAY_BUFFER,null),e.bindVertexArray(this.selectionVao),e.bindBuffer(e.ARRAY_BUFFER,this.selectionPosBuffer),e.enableVertexAttribArray(0),e.vertexAttribPointer(0,2,e.FLOAT,!1,0,0),e.bindBuffer(e.ARRAY_BUFFER,this.selectionLabelBuffer),e.enableVertexAttribArray(1),e.vertexAttribIPointer(1,1,e.UNSIGNED_SHORT,0,0),e.bindVertexArray(null),e.bindBuffer(e.ARRAY_BUFFER,null)}uploadDatasetToGPU(){let e=this.gl,t=this.dataset;if(!t)return;e.bindVertexArray(this.vao);let i=t.n<=this.maxGpuUploadPoints;if(this.gpuUsesFullDataset=i,i)e.bindBuffer(e.ARRAY_BUFFER,this.posBuffer),e.bufferData(e.ARRAY_BUFFER,t.positions,e.STATIC_DRAW),e.bindBuffer(e.ARRAY_BUFFER,this.labelBuffer),e.bufferData(e.ARRAY_BUFFER,t.labels,e.STATIC_DRAW),this.gpuPointCount=t.n;else{let i=t.n,r=Math.min(i,Math.max(25e4,Math.min(this.maxBaseDrawPoints,Math.floor(.25*i)))),o=Math.max(1,Math.floor(i/r)),s=Math.min(r,Math.ceil(i/o)),a=new Float32Array(2*s),n=new Uint16Array(s),l=0;for(let e=0;e<i&&l<s;e+=o)a[2*l]=t.positions[2*e],a[2*l+1]=t.positions[2*e+1],n[l]=t.labels[e],l++;e.bindBuffer(e.ARRAY_BUFFER,this.posBuffer),e.bufferData(e.ARRAY_BUFFER,a,e.STATIC_DRAW),e.bindBuffer(e.ARRAY_BUFFER,this.labelBuffer),e.bufferData(e.ARRAY_BUFFER,n,e.STATIC_DRAW),this.gpuPointCount=l}if(this.interactionCount=0,this.interactionEbo&&this.gpuUsesFullDataset){let i=t.n;if(i>=5e5){let t=Math.min(i,Math.max(25e4,Math.min(this.maxBaseDrawPoints,Math.floor(.25*i)))),r=Math.max(1,Math.floor(i/t)),o=Math.min(t,Math.ceil(i/r)),s=new Uint32Array(o),a=0;for(let e=0;e<i&&a<o;e+=r)s[a++]=e;this.interactionCount=a,e.bindBuffer(e.ELEMENT_ARRAY_BUFFER,this.interactionEbo),e.bufferData(e.ELEMENT_ARRAY_BUFFER,s,e.STATIC_DRAW),e.bindBuffer(e.ELEMENT_ARRAY_BUFFER,null)}}e.bindVertexArray(null),e.bindBuffer(e.ARRAY_BUFFER,null)}uploadSelectionToGPU(){if(!this.gl||!this.selectionEbo)return;let e=this.gl;if(!this.gpuUsesFullDataset){let t=this.dataset;if(!t||!this.selectionVao||!this.selectionPosBuffer||!this.selectionLabelBuffer)return;let i=this.selection.size;if(this.selectionOverlayCount=Math.min(i,25e4),0===i){this.selectionDirty=!1;return}let r=Math.min(i,25e4),o=new Float32Array(2*r),s=new Uint16Array(r),a=0;for(let e of this.selection)if(o[2*a]=t.positions[2*e],o[2*a+1]=t.positions[2*e+1],s[a]=t.labels[e],++a>=r)break;this.selectionOverlayCount=a,e.bindVertexArray(this.selectionVao),e.bindBuffer(e.ARRAY_BUFFER,this.selectionPosBuffer),e.bufferData(e.ARRAY_BUFFER,o,e.DYNAMIC_DRAW),e.bindBuffer(e.ARRAY_BUFFER,this.selectionLabelBuffer),e.bufferData(e.ARRAY_BUFFER,s,e.DYNAMIC_DRAW),e.bindVertexArray(null),e.bindBuffer(e.ARRAY_BUFFER,null),this.selectionDirty=!1;return}let t=Math.min(this.selection.size,25e4);if(this.selectionOverlayCount=t,0===t){this.selectionDirty=!1;return}let i=new Uint32Array(t),r=0;for(let e of this.selection)if(i[r++]=e,r>=t)break;this.selectionOverlayCount=r,e.bindBuffer(e.ELEMENT_ARRAY_BUFFER,this.selectionEbo),e.bufferData(e.ELEMENT_ARRAY_BUFFER,i,e.DYNAMIC_DRAW),e.bindBuffer(e.ELEMENT_ARRAY_BUFFER,null),this.selectionDirty=!1}uploadHoverToGPU(){if(!this.gl||!this.hoverEbo)return;let e=this.gl;if(!this.gpuUsesFullDataset){let t=this.dataset;if(!t||!this.hoverVao||!this.hoverPosBuffer||!this.hoverLabelBuffer)return;let i=this.hoveredIndex>=0&&this.hoveredIndex<t.n?this.hoveredIndex:-1,r=this.hoverPosScratch,o=this.hoverLabScratch;i>=0?(r[0]=t.positions[2*i],r[1]=t.positions[2*i+1],o[0]=t.labels[i]):(r[0]=2,r[1]=2,o[0]=0),e.bindVertexArray(this.hoverVao),e.bindBuffer(e.ARRAY_BUFFER,this.hoverPosBuffer),e.bufferData(e.ARRAY_BUFFER,r,e.DYNAMIC_DRAW),e.bindBuffer(e.ARRAY_BUFFER,this.hoverLabelBuffer),e.bufferData(e.ARRAY_BUFFER,o,e.DYNAMIC_DRAW),e.bindVertexArray(null),e.bindBuffer(e.ARRAY_BUFFER,null),this.hoverDirty=!1;return}let t=this.hoveredIndex>=0?this.hoveredIndex:0,i=this.hoverIndexScratch;i[0]=t,e.bindBuffer(e.ELEMENT_ARRAY_BUFFER,this.hoverEbo),e.bufferData(e.ELEMENT_ARRAY_BUFFER,i,e.DYNAMIC_DRAW),e.bindBuffer(e.ELEMENT_ARRAY_BUFFER,null),this.hoverDirty=!1}render(){this.ensureGL();let e=this.gl,t=this.dataset;if(!t)return;let i=performance.now()-this.lastViewChangeTs<80,r=!!this.interactionEbo&&this.interactionCount>0,o=i&&"poincare"===this.geometryKind()&&t.n>=2e6&&r,s=t.n>this.maxBaseDrawPoints&&r,l=this.gpuUsesFullDataset&&(o||s),h=this.gpuUsesFullDataset?l?this.interactionCount:t.n:this.gpuPointCount,u=this.estimatePointFragments(h,this.dpr);if(this.updateSquarePointPolicy(u),this.selectionDirty&&this.uploadSelectionToGPU(),this.hoverDirty&&this.uploadHoverToGPU(),e.bindFramebuffer(e.FRAMEBUFFER,null),e.viewport(0,0,this.canvas.width,this.canvas.height),e.disable(e.BLEND),"poincare"===this.geometryKind())if(this.renderBackdropIfNeeded(),this.backdropTex&&this.programComposite)e.useProgram(this.programComposite),e.activeTexture(e.TEXTURE0),e.bindTexture(e.TEXTURE_2D,this.backdropTex),this.uCompositeTex&&e.uniform1i(this.uCompositeTex,0),e.bindVertexArray(this.vao),e.drawArrays(e.TRIANGLES,0,3),e.bindTexture(e.TEXTURE_2D,null);else{let[t,i,r,o]=T(this.backgroundColor);e.clearColor(t,i,r,o),e.clear(e.COLOR_BUFFER_BIT)}else{let[t,i,r,o]=T(this.backgroundColor);e.clearColor(t,i,r,o),e.clear(e.COLOR_BUFFER_BIT)}if(this.ensurePointsResources(),!this.pointsFbo||!this.pointsTex||!this.programComposite)return;e.bindFramebuffer(e.FRAMEBUFFER,this.pointsFbo),e.viewport(0,0,this.pointsW,this.pointsH),e.clearColor(0,0,0,0),e.clear(e.COLOR_BUFFER_BIT);let d=this.renderAsSquares?this.pointsSquare:this.pointsCircle;if(d){if(e.useProgram(d.program),this.bindViewUniformsForProgram(d.program),this.paletteDirty&&this.uploadPaletteUniforms(),this.bindPaletteTexture(),d.uCssSize&&e.uniform2f(d.uCssSize,this.width,this.height),d.uDpr&&e.uniform1f(d.uDpr,this.dpr),d.uPointRadius&&e.uniform1f(d.uPointRadius,this.pointRadiusCss),this.renderAsSquares?e.disable(e.BLEND):(e.enable(e.BLEND),e.blendFunc(e.SRC_ALPHA,e.ONE_MINUS_SRC_ALPHA)),e.bindVertexArray(this.vao),l)e.bindBuffer(e.ELEMENT_ARRAY_BUFFER,this.interactionEbo),e.drawElements(e.POINTS,this.interactionCount,e.UNSIGNED_INT,0),e.bindBuffer(e.ELEMENT_ARRAY_BUFFER,null);else{let i=this.gpuUsesFullDataset?t.n:this.gpuPointCount;e.drawArrays(e.POINTS,0,i)}if(this.__debugPolicy={pointsDpr:this.dpr,deviceDpr:this.deviceDpr,canvasDpr:this.canvasDpr,renderAsSquares:this.renderAsSquares,useLod:l,baseDrawCount:h,interactionCount:this.interactionCount,gpuUsesFullDataset:this.gpuUsesFullDataset,gpuPointCount:this.gpuPointCount,estimatedPointFragments:u,fragmentBudget:this.policy.fragmentBudget,isInteracting:i},!i&&this.selection.size>0){if(e.useProgram(this.programSolid),this.bindViewUniformsForProgram(this.programSolid),this.uCssSizeSolid&&e.uniform2f(this.uCssSizeSolid,this.width,this.height),this.uDprSolid&&e.uniform1f(this.uDprSolid,this.dpr),this.uPointRadiusSolid&&e.uniform1f(this.uPointRadiusSolid,this.pointRadiusCss+1),this.uSolidColor){let[t,i,r,o]=T(a);e.uniform4f(this.uSolidColor,t,i,r,o)}this.uSolidRingMode&&e.uniform1i(this.uSolidRingMode,0),this.uSolidRingThicknessPx&&e.uniform1f(this.uSolidRingThicknessPx,0),this.uSolidPointSizePx&&e.uniform1f(this.uSolidPointSizePx,(this.pointRadiusCss+1)*2*this.dpr),this.gpuUsesFullDataset?(e.bindBuffer(e.ELEMENT_ARRAY_BUFFER,this.selectionEbo),e.drawElements(e.POINTS,this.selectionOverlayCount,e.UNSIGNED_INT,0),e.bindBuffer(e.ELEMENT_ARRAY_BUFFER,null)):this.selectionVao&&this.selectionOverlayCount>0&&(e.bindVertexArray(this.selectionVao),e.drawArrays(e.POINTS,0,this.selectionOverlayCount),e.bindVertexArray(this.vao))}if(!i&&this.hoveredIndex>=0&&this.hoveredIndex<t.n){e.useProgram(this.programSolid),this.bindViewUniformsForProgram(this.programSolid),this.uCssSizeSolid&&e.uniform2f(this.uCssSizeSolid,this.width,this.height),this.uDprSolid&&e.uniform1f(this.uDprSolid,this.dpr);let t=this.pointRadiusCss+3;if(this.uPointRadiusSolid&&e.uniform1f(this.uPointRadiusSolid,t),this.uSolidColor){let[t,i,r,o]=T(n);e.uniform4f(this.uSolidColor,t,i,r,o)}this.uSolidRingMode&&e.uniform1i(this.uSolidRingMode,1),this.uSolidRingThicknessPx&&e.uniform1f(this.uSolidRingThicknessPx,2),this.uSolidPointSizePx&&e.uniform1f(this.uSolidPointSizePx,2*t*this.dpr),this.gpuUsesFullDataset?(e.bindBuffer(e.ELEMENT_ARRAY_BUFFER,this.hoverEbo),e.drawElements(e.POINTS,1,e.UNSIGNED_INT,0)):this.hoverVao&&(e.bindVertexArray(this.hoverVao),e.drawArrays(e.POINTS,0,1),e.bindVertexArray(this.vao));let i=this.pointRadiusCss+1;if(this.selection.has(this.hoveredIndex)){if(this.uPointRadiusSolid&&e.uniform1f(this.uPointRadiusSolid,i),this.uSolidColor){let[t,i,r,o]=T(a);e.uniform4f(this.uSolidColor,t,i,r,o)}this.uSolidRingMode&&e.uniform1i(this.uSolidRingMode,0),this.uSolidRingThicknessPx&&e.uniform1f(this.uSolidRingThicknessPx,0),this.uSolidPointSizePx&&e.uniform1f(this.uSolidPointSizePx,2*i*this.dpr),this.gpuUsesFullDataset?e.drawElements(e.POINTS,1,e.UNSIGNED_INT,0):this.hoverVao&&(e.bindVertexArray(this.hoverVao),e.drawArrays(e.POINTS,0,1),e.bindVertexArray(this.vao))}else{let t=this.pointsCircle;if(!t)return;e.useProgram(t.program),this.bindViewUniformsForProgram(t.program),this.paletteDirty&&this.uploadPaletteUniforms(),this.bindPaletteTexture(),t.uCssSize&&e.uniform2f(t.uCssSize,this.width,this.height),t.uDpr&&e.uniform1f(t.uDpr,this.dpr),t.uPointRadius&&e.uniform1f(t.uPointRadius,i),this.gpuUsesFullDataset?e.drawElements(e.POINTS,1,e.UNSIGNED_INT,0):this.hoverVao&&(e.bindVertexArray(this.hoverVao),e.drawArrays(e.POINTS,0,1),e.bindVertexArray(this.vao))}this.gpuUsesFullDataset&&e.bindBuffer(e.ELEMENT_ARRAY_BUFFER,null)}e.bindFramebuffer(e.FRAMEBUFFER,null),e.viewport(0,0,this.canvas.width,this.canvas.height),e.useProgram(this.programComposite),e.activeTexture(e.TEXTURE0),e.bindTexture(e.TEXTURE_2D,this.pointsTex),this.uCompositeTex&&e.uniform1i(this.uCompositeTex,0),e.enable(e.BLEND),e.blendFunc(e.SRC_ALPHA,e.ONE_MINUS_SRC_ALPHA),e.bindVertexArray(this.vao),e.drawArrays(e.TRIANGLES,0,3),e.bindVertexArray(this.vao),e.bindTexture(e.TEXTURE_2D,null),e.bindVertexArray(null)}}}class w extends U{view={type:"euclidean",centerX:0,centerY:0,zoom:1};uniformCache=new Map;geometryKind(){return"euclidean"}setDataset(e){if("euclidean"!==e.geometry)throw Error("EuclideanWebGLCandidate only supports euclidean geometry");super.setDataset(e),this.fitToData()}fitToData(){let e=this.dataset;if(!e||0===e.n)return;let t=1/0,i=-1/0,r=1/0,o=-1/0;for(let s=0;s<e.n;s++){let a=e.positions[2*s],n=e.positions[2*s+1];t=Math.min(t,a),i=Math.max(i,a),r=Math.min(r,n),o=Math.max(o,n)}let s=Math.max(i-t||1,o-r||1);this.view={type:"euclidean",centerX:(t+i)/2,centerY:(r+o)/2,zoom:Math.max(.1,Math.min(100,2/s))}}setView(e){if("euclidean"!==e.type)throw Error("EuclideanWebGLCandidate only supports euclidean view state");this.view=e}getView(){return{...this.view}}bindViewUniformsForProgram(e){if(!this.gl)return;let t=this.gl,i=this.uniformCache.get(e);i||(i={uCenter:t.getUniformLocation(e,"u_center"),uZoom:t.getUniformLocation(e,"u_zoom")},this.uniformCache.set(e,i)),i.uCenter&&t.uniform2f(i.uCenter,this.view.centerX,this.view.centerY),i.uZoom&&t.uniform1f(i.uZoom,this.view.zoom)}pan(e,t,i){var r;let o;this.view=(r=this.view,o=.4*Math.min(this.width,this.height)*r.zoom,{...r,centerX:r.centerX-e/o,centerY:r.centerY+t/o}),this.markViewChanged()}zoom(e,t,i,r){var o,s,a;let n,l,h,u,f,c;this.view=(o=this.view,n=d(e,t,o,s=this.width,a=this.height),l=Math.pow(1.1,i),u=.4*Math.min(s,a)*(h=Math.max(.1,Math.min(100,o.zoom*l))),f=n.x-(e-s/2)/u,c=n.y+(t-a/2)/u,{...o,centerX:f,centerY:c,zoom:h}),this.markViewChanged()}hitTest(e,t){let i=this.dataset,r=this.dataIndex;if(!i||!r)return null;let o=this.pointRadiusCss+5,s=o*o,a=.4*Math.min(this.width,this.height)*this.view.zoom;if(!(a>0))return null;let n=o/a*(1+1e-12),l=n*n,h=d(e,t,this.view,this.width,this.height),f=.5*this.width,c=.5*this.height,p=this.view.centerX,m=this.view.centerY,x=-1,g=1/0;if(r.forEachInAABB(h.x-n,h.y-n,h.x+n,h.y+n,r=>{let o=i.positions[2*r],n=i.positions[2*r+1],u=o-h.x,d=n-h.y;if(u*u+d*d>l)return;let b=f+(o-p)*a-e,E=c-(n-m)*a-t,R=b*b+E*E;R<=s&&(R<g||R===g&&r<x)&&(g=R,x=r)}),x<0)return null;let b=u(i.positions[2*x],i.positions[2*x+1],this.view,this.width,this.height);return{index:x,screenX:b.x,screenY:b.y,distance:Math.sqrt(g)}}lassoSelect(e){let t=this.dataset,i=this.dataIndex;if(!t||!i)return l(new Set,0);let r=performance.now(),o=new Float32Array(e.length);for(let t=0;t<e.length/2;t++){let i=d(e[2*t],e[2*t+1],this.view,this.width,this.height);o[2*t]=i.x,o[2*t+1]=i.y}let s=1/0,a=1/0,n=-1/0,u=-1/0;for(let e=0;e<o.length;e+=2){let t=o[e],i=o[e+1];t<s&&(s=t),t>n&&(n=t),i<a&&(a=i),i>u&&(u=i)}let f={xMin:s,yMin:a,xMax:n,yMax:u},c=performance.now()-r;return h({type:"polygon",coords:o,bounds:f},t.positions,c,(e,t,i)=>!(e<f.xMin)&&!(e>f.xMax)&&!(t<f.yMin)&&!(t>f.yMax)&&g(e,t,i))}projectToScreen(e,t){return u(e,t,this.view,this.width,this.height)}unprojectFromScreen(e,t){return d(e,t,this.view,this.width,this.height)}}class k extends U{view=f();uniformCache=new Map;lastPanScreenX=0;lastPanScreenY=0;hasPanAnchor=!1;geometryKind(){return"poincare"}getBackdropZoom(){return this.view.displayZoom}setDataset(e){if("poincare"!==e.geometry)throw Error("HyperbolicWebGLCandidate only supports poincare geometry");super.setDataset(e),this.view=f(),this.hasPanAnchor=!1}setView(e){if("poincare"!==e.type)throw Error("HyperbolicWebGLCandidate only supports poincare view state");this.view=e,this.markBackdropDirty()}getView(){return{...this.view}}bindViewUniformsForProgram(e){if(!this.gl)return;let t=this.gl,i=this.uniformCache.get(e);i||(i={uA:t.getUniformLocation(e,"u_a"),uDisplayZoom:t.getUniformLocation(e,"u_displayZoom")},this.uniformCache.set(e,i)),i.uA&&t.uniform2f(i.uA,this.view.ax,this.view.ay),i.uDisplayZoom&&t.uniform1f(i.uDisplayZoom,this.view.displayZoom)}startPan(e,t){this.lastPanScreenX=e,this.lastPanScreenY=t,this.hasPanAnchor=!0}pan(e,t,i){this.hasPanAnchor||(this.lastPanScreenX=this.width/2,this.lastPanScreenY=this.height/2,this.hasPanAnchor=!0);let r=this.lastPanScreenX,o=this.lastPanScreenY,s=r+e,a=o+t;this.view=x(this.view,r,o,s,a,this.width,this.height),this.markViewChanged(),this.lastPanScreenX=s,this.lastPanScreenY=a}zoom(e,t,i,r){var o,s,a;let n,l,h,u,d,f,p,g;this.view=(o=this.view,s=this.width,a=this.height,n=Math.pow(1.1,i),l=Math.max(.5,Math.min(10,o.displayZoom*n)),h=m(e,t,o,s,a),u=.45*Math.min(s,a)*l,f=s/2+(d=c(h.x,h.y,o.ax,o.ay)).x*u,g=(p=a/2-d.y*u)-t,Math.abs(f-e)>.5||Math.abs(g)>.5?x({...o,displayZoom:l},f,p,e,t,s,a):{...o,displayZoom:l}),this.markViewChanged(),this.markBackdropDirty()}mobiusDerivativeScaleAt(e,t){let i=this.view.ax,r=this.view.ay,o=1-(i*e+r*t),s=-(i*t-r*e),a=o*o+s*s;return a<1e-12?0:Math.max(0,1-(i*i+r*r))/a}conservativeDataRadiusForScreenRadius(e,t,i,r){let o=this.view.ax,s=this.view.ay,a=o*o+s*s,n=Math.sqrt(a),l=Math.max(1e-12,1-a);if(!(r>1e-9)||!(i>0))return 0;let h=1-(o*e+s*t),u=-(o*t-s*e),d=Math.sqrt(h*h+u*u);if(!Number.isFinite(d)||d<1e-12)return 2;let f=i/(r*l),c=f*d*d;for(let e=0;e<5;e++){let e=d+n*c;c=f*e*e}return Number.isFinite(c)?Math.min(1.999,Math.max(0,c*=1.001)):2}hitTest(e,t){let i=this.dataset,r=this.dataIndex;if(!i||!r)return null;let{width:o,height:s,view:a}=this,n=o/2,l=s/2,h=.45*Math.min(o,s)*a.displayZoom,u=h*h,d=this.pointRadiusCss+5,f=d*d,c=e-n,p=t-l,x=h+d;if(c*c+p*p>x*x)return null;let g=m(e,t,a,o,s),b=this.conservativeDataRadiusForScreenRadius(g.x,g.y,d,h),E=-1,R=1/0,T=a.ax,y=a.ay;if(r.forEachInAABB(g.x-b,g.y-b,g.x+b,g.y+b,r=>{let o=i.positions[2*r],s=i.positions[2*r+1],a=o-T,d=s-y,c=1-(T*o+y*s),p=-(T*s-y*o),m=c*c+p*p,x=0,g=0;if(m<1e-12){let e=Math.sqrt(a*a+d*d);e<1e-12?(x=0,g=0):(x=a/e*.999,g=d/e*.999)}else{let e=(x=(a*c+d*p)/m)*x+(g=(d*c-a*p)/m)*g;if(e>=1){let t=Math.sqrt(e);x=x/t*.999,g=g/t*.999}}let b=n+x*h,_=l-g*h,v=b-n,A=_-l;if(v*v+A*A>u)return;let S=b-e,P=_-t,M=S*S+P*P;M<=f&&(M<R||M===R&&r<E)&&(R=M,E=r)}),E<0)return null;let _=i.positions[2*E],v=i.positions[2*E+1],A=_-T,S=v-y,P=1-(T*_+y*v),M=-(T*v-y*_),F=P*P+M*M,B=0,D=0;if(F<1e-12){let e=Math.sqrt(A*A+S*S);e<1e-12?(B=0,D=0):(B=A/e*.999,D=S/e*.999)}else{let e=(B=(A*P+S*M)/F)*B+(D=(S*P-A*M)/F)*D;if(e>=1){let t=Math.sqrt(e);B=B/t*.999,D=D/t*.999}}return{index:E,screenX:n+B*h,screenY:l-D*h,distance:Math.sqrt(R)}}lassoSelect(e){let t=this.dataset,i=this.dataIndex;if(!t||!i)return l(new Set,0);let r=performance.now(),o=new Float32Array(e.length);for(let t=0;t<e.length/2;t++){let i=m(e[2*t],e[2*t+1],this.view,this.width,this.height);o[2*t]=i.x,o[2*t+1]=i.y}let s=1/0,a=1/0,n=-1/0,u=-1/0;for(let e=0;e<o.length;e+=2){let t=o[e],i=o[e+1];t<s&&(s=t),t>n&&(n=t),i<a&&(a=i),i>u&&(u=i)}let d={xMin:s,yMin:a,xMax:n,yMax:u},f=performance.now()-r;return h({type:"polygon",coords:o,bounds:d},t.positions,f,(e,t,i)=>!(e<d.xMin)&&!(e>d.xMax)&&!(t<d.yMin)&&!(t>d.yMax)&&g(e,t,i))}projectToScreen(e,t){var i,r,o;let s,a;return i=this.view,r=this.width,o=this.height,s=c(e,t,i.ax,i.ay),a=.45*Math.min(r,o)*i.displayZoom,{x:r/2+s.x*a,y:o/2-s.y*a}}unprojectFromScreen(e,t){return m(e,t,this.view,this.width,this.height)}}function L(e,t){let i=Math.floor(e.length/2);if(i<=t)return new Float32Array(e);let r=e;if(i>2048){let t=new Float32Array(4096);for(let r=0;r<2048;r++){let o=Math.floor(r*i/2048);t[2*r]=e[2*o],t[2*r+1]=e[2*o+1]}r=t}let o=function(e,t){let i=Array.from(e),r=Math.floor(i.length/2);if(r<3)return i;for(let e=0;e<5&&!((r=Math.floor(i.length/2))<3);e++){let e=Array(4*r),t=0;for(let o=0;o<r;o++){let s=o,a=(o+1)%r,n=i[2*s],l=i[2*s+1],h=i[2*a],u=i[2*a+1];e[t++]=.75*n+.25*h,e[t++]=.75*l+.25*u,e[t++]=.25*n+.75*h,e[t++]=.25*l+.75*u}i=e}return i}(r,0),s=function(e){let t=1/0,i=1/0,r=-1/0,o=-1/0;for(let s=0;s<e.length;s+=2){let a=e[s],n=e[s+1];a<t&&(t=a),a>r&&(r=a),n<i&&(i=n),n>o&&(o=n)}return Number.isFinite(t)&&Number.isFinite(i)?{xMin:t,yMin:i,xMax:r,yMax:o}:{xMin:0,yMin:0,xMax:0,yMax:0}}(o),a=Math.max(s.xMax-s.xMin,s.yMax-s.yMin),n=(e,t,i,r,o,s)=>{let a=o-i,n=s-r,l=a*a+n*n,h=0;l>1e-12&&((h=((e-i)*a+(t-r)*n)/l)<0?h=0:h>1&&(h=1));let u=e-(i+h*a),d=t-(r+h*n);return u*u+d*d},l=e=>{let t=Math.floor(o.length/2);if(t<=2)return o.slice();let i=e*e,r=new Uint8Array(t);r[0]=1,r[t-1]=1;let s=[0,t-1];for(;s.length>0;){let e=s.pop(),t=s.pop(),a=o[2*t],l=o[2*t+1],h=o[2*e],u=o[2*e+1],d=-1,f=-1;for(let i=t+1;i<e;i++){let e=n(o[2*i],o[2*i+1],a,l,h,u);e>d&&(d=e,f=i)}d>i&&f>=0&&(r[f]=1,s.push(t,f),s.push(f,e))}let a=[];for(let e=0;e<t;e++)r[e]&&a.push(o[2*e],o[2*e+1]);return a},h=Math.max(1e-12,a/100),u=l(h),d=0;for(;Math.floor(u.length/2)>t&&d<20;)h*=1.1,u=l(h),d++;let f=Math.floor(u.length/2);if(f>t){let e=new Float32Array(2*t);for(let i=0;i<t;i++){let r=Math.floor(i*f/t);e[2*i]=u[2*r],e[2*i+1]=u[2*r+1]}return e}return new Float32Array(u)}function z(e){return{shift:e.shiftKey,ctrl:e.ctrlKey,alt:e.altKey,meta:e.metaKey}}function I(e){return Number.isFinite(e)?Math.max(1,Math.floor(e)):1}function N(e,t,i={}){let r=Number.isFinite(i.wheelZoomScale)?i.wheelZoomScale:.01,o=i.lassoPredicate??(e=>e.shiftKey&&(e.metaKey||e.ctrlKey)),s=Number.isFinite(i.lassoMinSampleDistPx)?i.lassoMinSampleDistPx:2,a=Number.isFinite(i.lassoMaxVertsInteraction)?i.lassoMaxVertsInteraction:24,n=Number.isFinite(i.lassoMaxVertsFinal)?i.lassoMaxVertsFinal:48,l=i.observeResize??!0,h=0,u=0,d=0,f=!0,c="idle",p=null,m=0,x=0,g=0,b=0,E={shift:!1,ctrl:!1,alt:!1,meta:!1},R=0,T=0,y=0,_={shift:!1,ctrl:!1,alt:!1,meta:!1},v=!1,A=!1,S=0,P=0,M=-2,F=[],B=null,D=0,C=0,U=!1,w=(t,i)=>{let r=e.getBoundingClientRect();return{x:t-r.left,y:i-r.top}},k=e=>{let i=new Float32Array(e.length);for(let r=0;r<e.length/2;r++){let o=e[2*r],s=e[2*r+1],a=t.projectToScreen(o,s);i[2*r]=a.x,i[2*r+1]=a.y}return i},X=()=>{h||(h=requestAnimationFrame(()=>{h=0;let r=!1;if(f){let i,o,s;f=!1,o=I((i=e.getBoundingClientRect()).width),s=I(i.height),r=(o!==u||s!==d)&&(u=o,d=s,t.resize(o,s),!0)||r}if((0!==g||0!==b)&&(t.pan(g,b,E),g=0,b=0,r=!0),v&&0!==R&&(t.zoom(T,y,R,_),R=0,v=!1,r=!0),"idle"===c&&A){A=!1;let e=t.hitTest(S,P),o=e?e.index:-1;o!==M&&(M=o,t.setHovered(o),r=!0),i.onHover?.(e)}if("lasso"===c&&U&&i.onLassoUpdate&&F.length>=6){U=!1;let e=L(F,a);B=e;let t=k(e);i.onLassoUpdate(e,t)}r&&t.render()}))},Y=i=>{if(0!==i.button)return;let{x:r,y:s}=w(i.clientX,i.clientY);if(p=i.pointerId,m=r,x=s,-1!==M&&(M=-1,t.setHovered(-1)),o(i)){c="lasso",F=[],B=null,D=r,C=s;let e=t.unprojectFromScreen(r,s);F.push(e.x,e.y),U=!0,X()}else c="pan",g=0,b=0,E=z(i),"startPan"in t&&t.startPan(r,s),X();e.setPointerCapture(i.pointerId)},V=e=>{if(p!==e.pointerId){if("idle"===c){let{x:t,y:i}=w(e.clientX,e.clientY);S=t,P=i,A=!0,X()}return}let{x:i,y:r}=w(e.clientX,e.clientY);if("pan"===c){g+=i-m,b+=r-x,E=z(e),m=i,x=r,X();return}if("lasso"===c){let e=i-D,o=r-C;if(e*e+o*o>=s*s){let e=t.unprojectFromScreen(i,r);F.push(e.x,e.y),U=!0,D=i,C=r,X()}return}S=i,P=r,A=!0,X()},W=r=>{if(p===r.pointerId){if("pan"===c&&(0!==g||0!==b)&&(t.pan(g,b,E),g=0,b=0,t.render()),"lasso"===c&&F.length>=6){let e=B??L(F,n),r=k(e),o=t.lassoSelect(r);i.onLassoComplete?.(o,e,r)}"endInteraction"in t&&t.endInteraction(),c="idle",p=null,F=[],B=null,U=!1,A=!1;try{e.releasePointerCapture(r.pointerId)}catch{}}},G=e=>{e.preventDefault();let{x:t,y:i}=w(e.clientX,e.clientY),o=-e.deltaY*r;R+=o,T=t,y=i,_=z(e),v=!0,X()};e.addEventListener("pointerdown",Y),e.addEventListener("pointermove",V),e.addEventListener("pointerup",W),e.addEventListener("pointercancel",W),e.addEventListener("wheel",G,{passive:!1});let O=null;return l&&"undefined"!=typeof ResizeObserver&&(O=new ResizeObserver(()=>{f=!0,X()})).observe(e),f=!0,X(),{destroy(){h&&(cancelAnimationFrame(h),h=0),e.removeEventListener("pointerdown",Y),e.removeEventListener("pointermove",V),e.removeEventListener("pointerup",W),e.removeEventListener("pointercancel",W),e.removeEventListener("wheel",G),O?.disconnect(),O=null},requestResize(){f=!0,X()}}}e.s(["DEFAULT_COLORS",0,s,"EuclideanWebGLCandidate",()=>w,"HOVER_COLOR",0,n,"HyperbolicWebGLCandidate",()=>k,"SELECTION_COLOR",0,a,"boundsOfPolygon",()=>b,"createDataset",()=>t,"createInteractionController",()=>N,"packPositions",()=>i,"packPositionsXY",()=>r,"packUint16Labels",()=>o,"pointInPolygon",()=>g],54214)}]);
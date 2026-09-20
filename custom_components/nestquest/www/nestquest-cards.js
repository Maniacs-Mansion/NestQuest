const T = globalThis, L = T.ShadowRoot && (T.ShadyCSS === void 0 || T.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, j = /* @__PURE__ */ Symbol(), K = /* @__PURE__ */ new WeakMap();
let ct = class {
  constructor(t, e, n) {
    if (this._$cssResult$ = !0, n !== j) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = t, this.t = e;
  }
  get styleSheet() {
    let t = this.o;
    const e = this.t;
    if (L && t === void 0) {
      const n = e !== void 0 && e.length === 1;
      n && (t = K.get(e)), t === void 0 && ((this.o = t = new CSSStyleSheet()).replaceSync(this.cssText), n && K.set(e, t));
    }
    return t;
  }
  toString() {
    return this.cssText;
  }
};
const $ = (s) => new ct(typeof s == "string" ? s : s + "", void 0, j), _t = (s, ...t) => {
  const e = s.length === 1 ? s[0] : t.reduce((n, i, r) => n + ((a) => {
    if (a._$cssResult$ === !0) return a.cssText;
    if (typeof a == "number") return a;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + a + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(i) + s[r + 1], s[0]);
  return new ct(e, s, j);
}, $t = (s, t) => {
  if (L) s.adoptedStyleSheets = t.map((e) => e instanceof CSSStyleSheet ? e : e.styleSheet);
  else for (const e of t) {
    const n = document.createElement("style"), i = T.litNonce;
    i !== void 0 && n.setAttribute("nonce", i), n.textContent = e.cssText, s.appendChild(n);
  }
}, J = L ? (s) => s : (s) => s instanceof CSSStyleSheet ? ((t) => {
  let e = "";
  for (const n of t.cssRules) e += n.cssText;
  return $(e);
})(s) : s;
const { is: vt, defineProperty: qt, getOwnPropertyDescriptor: xt, getOwnPropertyNames: wt, getOwnPropertySymbols: At, getPrototypeOf: kt } = Object, M = globalThis, G = M.trustedTypes, Et = G ? G.emptyScript : "", Ct = M.reactiveElementPolyfillSupport, E = (s, t) => s, F = { toAttribute(s, t) {
  switch (t) {
    case Boolean:
      s = s ? Et : null;
      break;
    case Object:
    case Array:
      s = s == null ? s : JSON.stringify(s);
  }
  return s;
}, fromAttribute(s, t) {
  let e = s;
  switch (t) {
    case Boolean:
      e = s !== null;
      break;
    case Number:
      e = s === null ? null : Number(s);
      break;
    case Object:
    case Array:
      try {
        e = JSON.parse(s);
      } catch {
        e = null;
      }
  }
  return e;
} }, ht = (s, t) => !vt(s, t), X = { attribute: !0, type: String, converter: F, reflect: !1, useDefault: !1, hasChanged: ht };
Symbol.metadata ??= /* @__PURE__ */ Symbol("metadata"), M.litPropertyMetadata ??= /* @__PURE__ */ new WeakMap();
let x = class extends HTMLElement {
  static addInitializer(t) {
    this._$Ei(), (this.l ??= []).push(t);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(t, e = X) {
    if (e.state && (e.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(t) && ((e = Object.create(e)).wrapped = !0), this.elementProperties.set(t, e), !e.noAccessor) {
      const n = /* @__PURE__ */ Symbol(), i = this.getPropertyDescriptor(t, n, e);
      i !== void 0 && qt(this.prototype, t, i);
    }
  }
  static getPropertyDescriptor(t, e, n) {
    const { get: i, set: r } = xt(this.prototype, t) ?? { get() {
      return this[e];
    }, set(a) {
      this[e] = a;
    } };
    return { get: i, set(a) {
      const l = i?.call(this);
      r?.call(this, a), this.requestUpdate(t, l, n);
    }, configurable: !0, enumerable: !0 };
  }
  static getPropertyOptions(t) {
    return this.elementProperties.get(t) ?? X;
  }
  static _$Ei() {
    if (this.hasOwnProperty(E("elementProperties"))) return;
    const t = kt(this);
    t.finalize(), t.l !== void 0 && (this.l = [...t.l]), this.elementProperties = new Map(t.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(E("finalized"))) return;
    if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(E("properties"))) {
      const e = this.properties, n = [...wt(e), ...At(e)];
      for (const i of n) this.createProperty(i, e[i]);
    }
    const t = this[Symbol.metadata];
    if (t !== null) {
      const e = litPropertyMetadata.get(t);
      if (e !== void 0) for (const [n, i] of e) this.elementProperties.set(n, i);
    }
    this._$Eh = /* @__PURE__ */ new Map();
    for (const [e, n] of this.elementProperties) {
      const i = this._$Eu(e, n);
      i !== void 0 && this._$Eh.set(i, e);
    }
    this.elementStyles = this.finalizeStyles(this.styles);
  }
  static finalizeStyles(t) {
    const e = [];
    if (Array.isArray(t)) {
      const n = new Set(t.flat(1 / 0).reverse());
      for (const i of n) e.unshift(J(i));
    } else t !== void 0 && e.push(J(t));
    return e;
  }
  static _$Eu(t, e) {
    const n = e.attribute;
    return n === !1 ? void 0 : typeof n == "string" ? n : typeof t == "string" ? t.toLowerCase() : void 0;
  }
  constructor() {
    super(), this._$Ep = void 0, this.isUpdatePending = !1, this.hasUpdated = !1, this._$Em = null, this._$Ev();
  }
  _$Ev() {
    this._$ES = new Promise((t) => this.enableUpdating = t), this._$AL = /* @__PURE__ */ new Map(), this._$E_(), this.requestUpdate(), this.constructor.l?.forEach((t) => t(this));
  }
  addController(t) {
    (this._$EO ??= /* @__PURE__ */ new Set()).add(t), this.renderRoot !== void 0 && this.isConnected && t.hostConnected?.();
  }
  removeController(t) {
    this._$EO?.delete(t);
  }
  _$E_() {
    const t = /* @__PURE__ */ new Map(), e = this.constructor.elementProperties;
    for (const n of e.keys()) this.hasOwnProperty(n) && (t.set(n, this[n]), delete this[n]);
    t.size > 0 && (this._$Ep = t);
  }
  createRenderRoot() {
    const t = this.shadowRoot ?? this.attachShadow(this.constructor.shadowRootOptions);
    return $t(t, this.constructor.elementStyles), t;
  }
  connectedCallback() {
    this.renderRoot ??= this.createRenderRoot(), this.enableUpdating(!0), this._$EO?.forEach((t) => t.hostConnected?.());
  }
  enableUpdating(t) {
  }
  disconnectedCallback() {
    this._$EO?.forEach((t) => t.hostDisconnected?.());
  }
  attributeChangedCallback(t, e, n) {
    this._$AK(t, n);
  }
  _$ET(t, e) {
    const n = this.constructor.elementProperties.get(t), i = this.constructor._$Eu(t, n);
    if (i !== void 0 && n.reflect === !0) {
      const r = (n.converter?.toAttribute !== void 0 ? n.converter : F).toAttribute(e, n.type);
      this._$Em = t, r == null ? this.removeAttribute(i) : this.setAttribute(i, r), this._$Em = null;
    }
  }
  _$AK(t, e) {
    const n = this.constructor, i = n._$Eh.get(t);
    if (i !== void 0 && this._$Em !== i) {
      const r = n.getPropertyOptions(i), a = typeof r.converter == "function" ? { fromAttribute: r.converter } : r.converter?.fromAttribute !== void 0 ? r.converter : F;
      this._$Em = i;
      const l = a.fromAttribute(e, r.type);
      this[i] = l ?? this._$Ej?.get(i) ?? l, this._$Em = null;
    }
  }
  requestUpdate(t, e, n, i = !1, r) {
    if (t !== void 0) {
      const a = this.constructor;
      if (i === !1 && (r = this[t]), n ??= a.getPropertyOptions(t), !((n.hasChanged ?? ht)(r, e) || n.useDefault && n.reflect && r === this._$Ej?.get(t) && !this.hasAttribute(a._$Eu(t, n)))) return;
      this.C(t, e, n);
    }
    this.isUpdatePending === !1 && (this._$ES = this._$EP());
  }
  C(t, e, { useDefault: n, reflect: i, wrapped: r }, a) {
    n && !(this._$Ej ??= /* @__PURE__ */ new Map()).has(t) && (this._$Ej.set(t, a ?? e ?? this[t]), r !== !0 || a !== void 0) || (this._$AL.has(t) || (this.hasUpdated || n || (e = void 0), this._$AL.set(t, e)), i === !0 && this._$Em !== t && (this._$Eq ??= /* @__PURE__ */ new Set()).add(t));
  }
  async _$EP() {
    this.isUpdatePending = !0;
    try {
      await this._$ES;
    } catch (e) {
      Promise.reject(e);
    }
    const t = this.scheduleUpdate();
    return t != null && await t, !this.isUpdatePending;
  }
  scheduleUpdate() {
    return this.performUpdate();
  }
  performUpdate() {
    if (!this.isUpdatePending) return;
    if (!this.hasUpdated) {
      if (this.renderRoot ??= this.createRenderRoot(), this._$Ep) {
        for (const [i, r] of this._$Ep) this[i] = r;
        this._$Ep = void 0;
      }
      const n = this.constructor.elementProperties;
      if (n.size > 0) for (const [i, r] of n) {
        const { wrapped: a } = r, l = this[i];
        a !== !0 || this._$AL.has(i) || l === void 0 || this.C(i, void 0, r, l);
      }
    }
    let t = !1;
    const e = this._$AL;
    try {
      t = this.shouldUpdate(e), t ? (this.willUpdate(e), this._$EO?.forEach((n) => n.hostUpdate?.()), this.update(e)) : this._$EM();
    } catch (n) {
      throw t = !1, this._$EM(), n;
    }
    t && this._$AE(e);
  }
  willUpdate(t) {
  }
  _$AE(t) {
    this._$EO?.forEach((e) => e.hostUpdated?.()), this.hasUpdated || (this.hasUpdated = !0, this.firstUpdated(t)), this.updated(t);
  }
  _$EM() {
    this._$AL = /* @__PURE__ */ new Map(), this.isUpdatePending = !1;
  }
  get updateComplete() {
    return this.getUpdateComplete();
  }
  getUpdateComplete() {
    return this._$ES;
  }
  shouldUpdate(t) {
    return !0;
  }
  update(t) {
    this._$Eq &&= this._$Eq.forEach((e) => this._$ET(e, this[e])), this._$EM();
  }
  updated(t) {
  }
  firstUpdated(t) {
  }
};
x.elementStyles = [], x.shadowRootOptions = { mode: "open" }, x[E("elementProperties")] = /* @__PURE__ */ new Map(), x[E("finalized")] = /* @__PURE__ */ new Map(), Ct?.({ ReactiveElement: x }), (M.reactiveElementVersions ??= []).push("2.1.2");
const B = globalThis, Y = (s) => s, z = B.trustedTypes, tt = z ? z.createPolicy("lit-html", { createHTML: (s) => s }) : void 0, ut = "$lit$", y = `lit$${Math.random().toFixed(9).slice(2)}$`, ft = "?" + y, St = `<${ft}>`, q = document, C = () => q.createComment(""), S = (s) => s === null || typeof s != "object" && typeof s != "function", Q = Array.isArray, Nt = (s) => Q(s) || typeof s?.[Symbol.iterator] == "function", D = `[ 	
\f\r]`, k = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, et = /-->/g, nt = />/g, b = RegExp(`>|${D}(?:([^\\s"'>=/]+)(${D}*=${D}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g"), st = /'/g, it = /"/g, gt = /^(?:script|style|textarea|title)$/i, Pt = (s) => (t, ...e) => ({ _$litType$: s, strings: t, values: e }), g = Pt(1), w = /* @__PURE__ */ Symbol.for("lit-noChange"), c = /* @__PURE__ */ Symbol.for("lit-nothing"), rt = /* @__PURE__ */ new WeakMap(), _ = q.createTreeWalker(q, 129);
function mt(s, t) {
  if (!Q(s) || !s.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return tt !== void 0 ? tt.createHTML(t) : t;
}
const Tt = (s, t) => {
  const e = s.length - 1, n = [];
  let i, r = t === 2 ? "<svg>" : t === 3 ? "<math>" : "", a = k;
  for (let l = 0; l < e; l++) {
    const o = s[l];
    let d, h, p = -1, f = 0;
    for (; f < o.length && (a.lastIndex = f, h = a.exec(o), h !== null); ) f = a.lastIndex, a === k ? h[1] === "!--" ? a = et : h[1] !== void 0 ? a = nt : h[2] !== void 0 ? (gt.test(h[2]) && (i = RegExp("</" + h[2], "g")), a = b) : h[3] !== void 0 && (a = b) : a === b ? h[0] === ">" ? (a = i ?? k, p = -1) : h[1] === void 0 ? p = -2 : (p = a.lastIndex - h[2].length, d = h[1], a = h[3] === void 0 ? b : h[3] === '"' ? it : st) : a === it || a === st ? a = b : a === et || a === nt ? a = k : (a = b, i = void 0);
    const u = a === b && s[l + 1].startsWith("/>") ? " " : "";
    r += a === k ? o + St : p >= 0 ? (n.push(d), o.slice(0, p) + ut + o.slice(p) + y + u) : o + y + (p === -2 ? l : u);
  }
  return [mt(s, r + (s[e] || "<?>") + (t === 2 ? "</svg>" : t === 3 ? "</math>" : "")), n];
};
class N {
  constructor({ strings: t, _$litType$: e }, n) {
    let i;
    this.parts = [];
    let r = 0, a = 0;
    const l = t.length - 1, o = this.parts, [d, h] = Tt(t, e);
    if (this.el = N.createElement(d, n), _.currentNode = this.el.content, e === 2 || e === 3) {
      const p = this.el.content.firstChild;
      p.replaceWith(...p.childNodes);
    }
    for (; (i = _.nextNode()) !== null && o.length < l; ) {
      if (i.nodeType === 1) {
        if (i.hasAttributes()) for (const p of i.getAttributeNames()) if (p.endsWith(ut)) {
          const f = h[a++], u = i.getAttribute(p).split(y), m = /([.?@])?(.*)/.exec(f);
          o.push({ type: 1, index: r, name: m[2], strings: u, ctor: m[1] === "." ? Ot : m[1] === "?" ? Mt : m[1] === "@" ? Ut : U }), i.removeAttribute(p);
        } else p.startsWith(y) && (o.push({ type: 6, index: r }), i.removeAttribute(p));
        if (gt.test(i.tagName)) {
          const p = i.textContent.split(y), f = p.length - 1;
          if (f > 0) {
            i.textContent = z ? z.emptyScript : "";
            for (let u = 0; u < f; u++) i.append(p[u], C()), _.nextNode(), o.push({ type: 2, index: ++r });
            i.append(p[f], C());
          }
        }
      } else if (i.nodeType === 8) if (i.data === ft) o.push({ type: 2, index: r });
      else {
        let p = -1;
        for (; (p = i.data.indexOf(y, p + 1)) !== -1; ) o.push({ type: 7, index: r }), p += y.length - 1;
      }
      r++;
    }
  }
  static createElement(t, e) {
    const n = q.createElement("template");
    return n.innerHTML = t, n;
  }
}
function A(s, t, e = s, n) {
  if (t === w) return t;
  let i = n !== void 0 ? e._$Co?.[n] : e._$Cl;
  const r = S(t) ? void 0 : t._$litDirective$;
  return i?.constructor !== r && (i?._$AO?.(!1), r === void 0 ? i = void 0 : (i = new r(s), i._$AT(s, e, n)), n !== void 0 ? (e._$Co ??= [])[n] = i : e._$Cl = i), i !== void 0 && (t = A(s, i._$AS(s, t.values), i, n)), t;
}
class zt {
  constructor(t, e) {
    this._$AV = [], this._$AN = void 0, this._$AD = t, this._$AM = e;
  }
  get parentNode() {
    return this._$AM.parentNode;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  u(t) {
    const { el: { content: e }, parts: n } = this._$AD, i = (t?.creationScope ?? q).importNode(e, !0);
    _.currentNode = i;
    let r = _.nextNode(), a = 0, l = 0, o = n[0];
    for (; o !== void 0; ) {
      if (a === o.index) {
        let d;
        o.type === 2 ? d = new P(r, r.nextSibling, this, t) : o.type === 1 ? d = new o.ctor(r, o.name, o.strings, this, t) : o.type === 6 && (d = new Ht(r, this, t)), this._$AV.push(d), o = n[++l];
      }
      a !== o?.index && (r = _.nextNode(), a++);
    }
    return _.currentNode = q, i;
  }
  p(t) {
    let e = 0;
    for (const n of this._$AV) n !== void 0 && (n.strings !== void 0 ? (n._$AI(t, n, e), e += n.strings.length - 2) : n._$AI(t[e])), e++;
  }
}
class P {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(t, e, n, i) {
    this.type = 2, this._$AH = c, this._$AN = void 0, this._$AA = t, this._$AB = e, this._$AM = n, this.options = i, this._$Cv = i?.isConnected ?? !0;
  }
  get parentNode() {
    let t = this._$AA.parentNode;
    const e = this._$AM;
    return e !== void 0 && t?.nodeType === 11 && (t = e.parentNode), t;
  }
  get startNode() {
    return this._$AA;
  }
  get endNode() {
    return this._$AB;
  }
  _$AI(t, e = this) {
    t = A(this, t, e), S(t) ? t === c || t == null || t === "" ? (this._$AH !== c && this._$AR(), this._$AH = c) : t !== this._$AH && t !== w && this._(t) : t._$litType$ !== void 0 ? this.$(t) : t.nodeType !== void 0 ? this.T(t) : Nt(t) ? this.k(t) : this._(t);
  }
  O(t) {
    return this._$AA.parentNode.insertBefore(t, this._$AB);
  }
  T(t) {
    this._$AH !== t && (this._$AR(), this._$AH = this.O(t));
  }
  _(t) {
    this._$AH !== c && S(this._$AH) ? this._$AA.nextSibling.data = t : this.T(q.createTextNode(t)), this._$AH = t;
  }
  $(t) {
    const { values: e, _$litType$: n } = t, i = typeof n == "number" ? this._$AC(t) : (n.el === void 0 && (n.el = N.createElement(mt(n.h, n.h[0]), this.options)), n);
    if (this._$AH?._$AD === i) this._$AH.p(e);
    else {
      const r = new zt(i, this), a = r.u(this.options);
      r.p(e), this.T(a), this._$AH = r;
    }
  }
  _$AC(t) {
    let e = rt.get(t.strings);
    return e === void 0 && rt.set(t.strings, e = new N(t)), e;
  }
  k(t) {
    Q(this._$AH) || (this._$AH = [], this._$AR());
    const e = this._$AH;
    let n, i = 0;
    for (const r of t) i === e.length ? e.push(n = new P(this.O(C()), this.O(C()), this, this.options)) : n = e[i], n._$AI(r), i++;
    i < e.length && (this._$AR(n && n._$AB.nextSibling, i), e.length = i);
  }
  _$AR(t = this._$AA.nextSibling, e) {
    for (this._$AP?.(!1, !0, e); t !== this._$AB; ) {
      const n = Y(t).nextSibling;
      Y(t).remove(), t = n;
    }
  }
  setConnected(t) {
    this._$AM === void 0 && (this._$Cv = t, this._$AP?.(t));
  }
}
class U {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(t, e, n, i, r) {
    this.type = 1, this._$AH = c, this._$AN = void 0, this.element = t, this.name = e, this._$AM = i, this.options = r, n.length > 2 || n[0] !== "" || n[1] !== "" ? (this._$AH = Array(n.length - 1).fill(new String()), this.strings = n) : this._$AH = c;
  }
  _$AI(t, e = this, n, i) {
    const r = this.strings;
    let a = !1;
    if (r === void 0) t = A(this, t, e, 0), a = !S(t) || t !== this._$AH && t !== w, a && (this._$AH = t);
    else {
      const l = t;
      let o, d;
      for (t = r[0], o = 0; o < r.length - 1; o++) d = A(this, l[n + o], e, o), d === w && (d = this._$AH[o]), a ||= !S(d) || d !== this._$AH[o], d === c ? t = c : t !== c && (t += (d ?? "") + r[o + 1]), this._$AH[o] = d;
    }
    a && !i && this.j(t);
  }
  j(t) {
    t === c ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, t ?? "");
  }
}
class Ot extends U {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(t) {
    this.element[this.name] = t === c ? void 0 : t;
  }
}
class Mt extends U {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(t) {
    this.element.toggleAttribute(this.name, !!t && t !== c);
  }
}
class Ut extends U {
  constructor(t, e, n, i, r) {
    super(t, e, n, i, r), this.type = 5;
  }
  _$AI(t, e = this) {
    if ((t = A(this, t, e, 0) ?? c) === w) return;
    const n = this._$AH, i = t === c && n !== c || t.capture !== n.capture || t.once !== n.once || t.passive !== n.passive, r = t !== c && (n === c || i);
    i && this.element.removeEventListener(this.name, this, n), r && this.element.addEventListener(this.name, this, t), this._$AH = t;
  }
  handleEvent(t) {
    typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, t) : this._$AH.handleEvent(t);
  }
}
class Ht {
  constructor(t, e, n) {
    this.element = t, this.type = 6, this._$AN = void 0, this._$AM = e, this.options = n;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t) {
    A(this, t);
  }
}
const Dt = B.litHtmlPolyfillSupport;
Dt?.(N, P), (B.litHtmlVersions ??= []).push("3.3.3");
const Rt = (s, t, e) => {
  const n = e?.renderBefore ?? t;
  let i = n._$litPart$;
  if (i === void 0) {
    const r = e?.renderBefore ?? null;
    n._$litPart$ = i = new P(t.insertBefore(C(), r), r, void 0, e ?? {});
  }
  return i._$AI(s), i;
};
const W = globalThis;
class v extends x {
  constructor() {
    super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
  }
  createRenderRoot() {
    const t = super.createRenderRoot();
    return this.renderOptions.renderBefore ??= t.firstChild, t;
  }
  update(t) {
    const e = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t), this._$Do = Rt(e, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(!0);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(!1);
  }
  render() {
    return w;
  }
}
v._$litElement$ = !0, v.finalized = !0, W.litElementHydrateSupport?.({ LitElement: v });
const It = W.litElementPolyfillSupport;
It?.({ LitElement: v });
(W.litElementVersions ??= []).push("4.2.2");
const yt = ':host{--nq-p-parchment-top: #f0e4c7;--nq-p-parchment-bottom: #ddcca3;--nq-p-parchment: radial-gradient(ellipse at 25% 10%, rgba(255,255,255,.5), transparent 55%), radial-gradient(ellipse at 85% 90%, rgba(120,86,44,.28), transparent 60%), repeating-linear-gradient(93deg, rgba(150,115,70,.05) 0 2px, transparent 2px 6px), repeating-linear-gradient(2deg, rgba(150,115,70,.04) 0 3px, transparent 3px 7px), linear-gradient(var(--nq-p-parchment-top), var(--nq-p-parchment-bottom));--nq-p-vignette: inset 0 0 200px rgba(80,52,20,.35);--nq-p-card-open: linear-gradient(#fdf7e6, #f2e7c9);--nq-p-card-done: linear-gradient(#f0e8d3, #e6dcc2);--nq-p-card-panel: linear-gradient(#fcf6e6, #f1e6ca);--nq-p-card-border: rgba(120,88,48,.38);--nq-p-panel-border: rgba(92,62,26,.4);--nq-p-card-shadow: 0 3px 0 rgba(120,88,48,.2), inset 0 1px 0 rgba(255,255,255,.7);--nq-p-panel-shadow: 0 6px 0 rgba(92,62,26,.18), inset 0 2px 0 rgba(255,255,255,.7);--nq-p-frame-outer: 2px solid rgba(92,62,26,.45);--nq-p-frame-inner: 1px solid rgba(92,62,26,.28);--nq-p-rule: 2px solid rgba(92,62,26,.35);--nq-p-ink: #2b1f14;--nq-p-ink-secondary: #5c452a;--nq-p-ink-muted: #6f6455;--nq-p-ink-away: #4d4433;--nq-p-ink-late: #8f1526;--nq-brand-blue: #3B3AB8;--nq-brand-purple: #A035CC;--nq-brand-gradient: linear-gradient(135deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-p-icon-tile: var(--nq-brand-gradient);--nq-p-icon-tile-done: rgba(92,62,26,.16);--nq-p-crest: var(--nq-brand-gradient);--nq-p-crest-away: linear-gradient(135deg, #6b6b7a, #7a7286);--nq-p-seal: radial-gradient(circle at 35% 30%, #a8283a, #6d1322);--nq-p-seal-shadow: 0 4px 10px rgba(60,10,20,.4), inset 0 0 0 4px rgba(255,255,255,.14);--nq-p-seal-size: 78px;--nq-p-dock-bg: rgba(43,31,20,.9);--nq-p-dock-ink: #f7efdb;--nq-p-dock-ink-secondary: #d8c9a6;--nq-p-dock-divider: rgba(233,220,189,.3);--nq-p-dock-height: 84px;--nq-p-font-display: "Cinzel Decorative", Cinzel, serif;--nq-p-font-heading: Cinzel, serif;--nq-p-font-body: Nunito, system-ui, sans-serif;--nq-p-size-hero: 86px;--nq-p-size-wordmark: 66px;--nq-p-size-title: 56px;--nq-p-size-name: 48px;--nq-p-size-section: 32px;--nq-p-size-quest: 30px;--nq-p-size-body: 22px;--nq-p-size-label: 21px;--nq-p-track-label: .14em;--nq-p-track-kicker: .3em;--nq-p-quest-min-height: 116px;--nq-p-quest-gap: 24px;--nq-p-button-height: 72px;--nq-p-button-min-width: 150px;--nq-p-confirm-button: 108px;--nq-p-radius-card: 12px;--nq-p-radius-panel: 20px;--nq-p-radius-pill: 9999px;--nq-p-page-inset: 62px;--nq-p-frame-inset: 26px;--nq-ease-out: cubic-bezier(0, 0, .2, 1);--nq-dur-micro: .12s;--nq-dur-base: .2s;--nq-dur-modal: .35s}';
function V(s) {
  window.customCards = window.customCards ?? [], window.customCards.push(s);
}
const at = /* @__PURE__ */ new Map();
function O(s, t) {
  const e = `${s ?? "local"}|${JSON.stringify(t)}`, n = at.get(e);
  if (n)
    return n;
  let i;
  try {
    i = new Intl.DateTimeFormat("en-US", {
      ...t,
      ...s ? { timeZone: s } : {}
    });
  } catch {
    i = new Intl.DateTimeFormat("en-US", t);
  }
  return at.set(e, i), i;
}
function Ft(s) {
  const t = s?.config;
  if (!t || typeof t != "object")
    return;
  const e = t.time_zone;
  return typeof e == "string" && e.trim() ? e.trim() : void 0;
}
function R(s, t) {
  return `${O(t, { weekday: "long" }).format(s)}, ${O(t, { month: "short", day: "numeric" }).format(s)}`;
}
function Lt(s, t) {
  return O(t, {
    hour: "numeric",
    minute: "2-digit",
    hour12: !0
  }).format(s);
}
const jt = {
  "clear-night": "Clear",
  cloudy: "Cloudy",
  exceptional: "Clear",
  fog: "Foggy",
  hail: "Hail",
  lightning: "Storms",
  "lightning-rimmed": "Storms",
  partlycloudy: "Partly cloudy",
  pouring: "Heavy rain",
  rainy: "Rain",
  snowy: "Snow",
  "snowy-rainy": "Sleet",
  sunny: "Sunny",
  windy: "Windy",
  "windy-variant": "Windy"
}, Bt = {
  "clear-night": "Clear night skies",
  cloudy: "Grey skies today",
  exceptional: "A striking day",
  fog: "Mist on the road",
  hail: "Ice from the sky",
  lightning: "Storms may roll in",
  "lightning-rimmed": "Storms may roll in",
  partlycloudy: "Sun between clouds",
  pouring: "Heavy rain outside",
  rainy: "Rain on the walls",
  snowy: "Snow on the peaks",
  "snowy-rainy": "Sleet may fall",
  sunny: "Clear skies today",
  windy: "A blustery day",
  "windy-variant": "A blustery day"
};
function ot(s) {
  return typeof s == "string" ? s.trim() : "";
}
function I(s, t) {
  if (s == null || s === "")
    return t;
  const e = typeof s == "number" ? s : Number(s);
  return Number.isFinite(e) ? e : t;
}
function lt(s) {
  return Number.isFinite(s) ? Math.min(100, Math.max(0, s)) : 0;
}
function pt(s) {
  return Math.max(0, Math.round(s));
}
function Qt(s) {
  return s.split(/[-_]+/).filter(Boolean).map((t) => t.charAt(0).toUpperCase() + t.slice(1)).join(" ");
}
function Wt(s, t) {
  const e = O(t, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23"
  }).formatToParts(new Date(s)), n = (r) => {
    const a = e.find((l) => l.type === r);
    return a ? Number(a.value) : Number.NaN;
  }, i = Date.UTC(
    n("year"),
    n("month") - 1,
    n("day"),
    n("hour"),
    n("minute"),
    n("second")
  );
  return Number.isFinite(i) ? i - s : 0;
}
function Vt(s, t) {
  if (typeof s != "string")
    return null;
  const e = s.split("-");
  if (e.length !== 3)
    return null;
  const [n, i, r] = e.map((o) => Number(o));
  if (!n || !i || !r)
    return null;
  if (!t) {
    const o = new Date(n, i - 1, r);
    return Number.isNaN(o.getTime()) ? null : o;
  }
  let a = Date.UTC(n, i - 1, r);
  for (let o = 0; o < 2; o += 1)
    a -= Wt(a, t);
  const l = new Date(a);
  return Number.isNaN(l.getTime()) ? null : l;
}
function Zt(s) {
  const t = jt[s];
  return t || s.charAt(0).toUpperCase() + s.slice(1);
}
function Kt(s, t) {
  return Bt[s] ?? t;
}
const dt = "polygon(0 0, 100% 0, 100% 62%, 50% 100%, 0 62%)", Jt = "polygon(50% 0, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)", Gt = _t`
  * {
    box-sizing: border-box;
  }

  :host {
    display: block;
    height: 100%;
    --nq-brand-gradient-h: linear-gradient(
      90deg,
      var(--nq-brand-blue),
      var(--nq-brand-purple)
    );
  }

  .board {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    height: 1080px;
    padding: 0;
    overflow: hidden;
    background: var(--nq-p-parchment);
    box-shadow: var(--nq-p-vignette);
    font-family: var(--nq-p-font-body);
  }

  .frame {
    position: absolute;
    pointer-events: none;
  }

  .frame-outer {
    inset: 26px;
    border: var(--nq-p-frame-outer);
    border-radius: 14px;
  }

  .frame-inner {
    inset: 36px;
    border: var(--nq-p-frame-inner);
    border-radius: 8px;
  }

  .wordmark-row {
    position: absolute;
    top: 64px;
    left: 0;
    right: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 26px;
    width: 100%;
  }

  .rule {
    flex: 1 1 0;
    max-width: 340px;
    height: 2px;
    border-radius: 1px;
    background: rgba(92, 62, 26, 0.35);
  }

  .d20 {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    clip-path: ${$(Jt)};
    background: var(--nq-brand-gradient);
  }

  .d20-numeral {
    font-family: var(--nq-p-font-heading);
    font-size: 15px;
    font-weight: 700;
    line-height: 1;
    color: #ffffff;
  }

  .wordmark {
    font-family: var(--nq-p-font-display);
    font-size: var(--nq-p-size-wordmark);
    font-weight: 900;
    line-height: 1.15;
    background: var(--nq-brand-gradient);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    -webkit-text-fill-color: transparent;
  }

  .kicker {
    position: absolute;
    top: 154px;
    left: 0;
    right: 0;
    font-family: var(--nq-p-font-heading);
    font-size: 22px;
    font-weight: 600;
    letter-spacing: var(--nq-p-track-kicker);
    text-transform: uppercase;
    line-height: 1.2;
    text-align: center;
    color: var(--nq-p-ink-secondary);
  }

  .plates {
    position: absolute;
    top: 262px;
    left: 110px;
    right: 110px;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 56px;
  }

  .plate {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 26px;
    height: 600px;
    padding: 44px 28px 40px;
    border: 2px solid var(--nq-p-panel-border);
    border-radius: var(--nq-p-radius-panel);
    background: var(--nq-p-card-panel);
    box-shadow: var(--nq-p-panel-shadow);
    font: inherit;
  }

  button.plate {
    width: 100%;
    color: inherit;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    transition: transform var(--nq-dur-micro) var(--nq-ease-out);
  }

  button.plate:active {
    transform: scale(0.98);
  }

  button.plate:focus-visible {
    outline: 3px solid var(--nq-brand-purple);
    outline-offset: 4px;
  }

  .plate.away {
    border: 2px dashed var(--nq-p-panel-border);
    background: linear-gradient(#f2ecdd, #e6dcc6);
    box-shadow: none;
  }

  .crest {
    position: relative;
    flex: none;
    width: 188px;
    height: 214px;
    padding: 4px;
    clip-path: ${$(dt)};
    background: rgba(255, 255, 255, 0.22);
  }

  .crest-face {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-bottom: 70px;
    clip-path: ${$(dt)};
    background: var(--nq-p-crest);
  }

  .crest.away .crest-face {
    background: var(--nq-p-crest-away);
  }

  .crest .initial {
    font-family: var(--nq-p-font-display);
    font-size: 82px;
    font-weight: 700;
    line-height: 1;
    color: #ffffff;
  }

  .name {
    font-family: var(--nq-p-font-heading);
    font-size: var(--nq-p-size-name);
    font-weight: 700;
    letter-spacing: 0.02em;
    line-height: 1.1;
    color: var(--nq-p-ink);
  }

  .plate.away .name {
    color: var(--nq-p-ink-away);
  }

  .pill {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 8px 20px;
    border-radius: var(--nq-p-radius-pill);
    background: rgba(22, 120, 60, 0.35);
    font-family: var(--nq-p-font-heading);
    font-size: 22px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    line-height: 1;
    color: #146b36;
  }

  .pill svg {
    width: 22px;
    height: 22px;
    color: #157a3c;
  }

  .pill.away {
    background: rgba(92, 62, 26, 0.16);
    color: var(--nq-p-ink-away);
  }

  .pill.away svg {
    color: var(--nq-p-ink-away);
  }

  .progress-line {
    font-family: var(--nq-p-font-heading);
    font-size: 24px;
    font-weight: 700;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .bar {
    width: 100%;
    height: 16px;
    border: 1px solid rgba(92, 62, 26, 0.35);
    border-radius: var(--nq-p-radius-pill);
    background: rgba(92, 62, 26, 0.18);
    overflow: hidden;
  }

  .bar .fill {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: var(--nq-brand-gradient-h);
  }

  .hint {
    position: absolute;
    top: 930px;
    left: 0;
    right: 0;
    font-family: var(--nq-p-font-body);
    font-size: 24px;
    font-weight: 600;
    line-height: 1.4;
    text-align: center;
    color: var(--nq-p-ink-secondary);
  }

  .spacer {
    flex: 1 1 0;
  }

  .dock {
    position: absolute;
    left: 46px;
    right: 46px;
    bottom: 46px;
    height: var(--nq-p-dock-height);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 24px;
    padding: 0 40px;
    border-radius: 14px;
    background: var(--nq-p-dock-bg);
    pointer-events: none;
    user-select: none;
    color: var(--nq-p-dock-ink);
  }

  .dock svg {
    flex: none;
    width: 40px;
    height: 40px;
    color: var(--nq-p-dock-ink);
  }

  .dock .divider {
    flex: none;
    width: 1px;
    height: 40px;
    background: var(--nq-p-dock-divider);
  }

  .dock .temp {
    font-family: var(--nq-p-font-body);
    font-size: 38px;
    font-weight: 800;
    line-height: 1;
  }

  .dock .condition {
    font-family: var(--nq-p-font-body);
    font-size: 26px;
    font-weight: 600;
    line-height: 1.2;
    color: var(--nq-p-dock-ink-secondary);
  }

  .dock .date {
    font-family: var(--nq-p-font-body);
    font-size: 26px;
    font-weight: 600;
    line-height: 1.2;
    color: var(--nq-p-dock-ink-secondary);
  }

  .dock .clock {
    font-family: var(--nq-p-font-body);
    font-size: 38px;
    font-weight: 800;
    line-height: 1;
  }
`, Xt = g`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <circle cx="12" cy="12" r="10"></circle>
  <path d="m9 12 2 2 4-4"></path>
</svg>`, Yt = g`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M3.5 21 12 3.5 20.5 21"></path>
  <path d="M9 21l3-8 3 8"></path>
</svg>`, te = g`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M12 2v2"></path>
  <path d="m4.93 4.93 1.41 1.41"></path>
  <path d="M20 12h2"></path>
  <path d="m19.07 4.93-1.41 1.41"></path>
  <path d="M15.947 12.65a4 4 0 0 0-5.925-4.128"></path>
  <path d="M13 22H7a5 5 0 1 1 4.9-6H13a3 3 0 0 1 0 6Z"></path>
</svg>`;
class ee extends v {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 },
    _now: { state: !0 }
  };
  static styles = [$(yt), Gt];
  hass;
  _config;
  _now = /* @__PURE__ */ new Date();
  _clockTimer;
  setConfig(t) {
    if (!t || typeof t != "object")
      throw new Error("Invalid configuration");
    this._config = t;
  }
  getCardSize() {
    return 6;
  }
  connectedCallback() {
    super.connectedCallback(), this._now = /* @__PURE__ */ new Date(), this._clockTimer = window.setInterval(() => {
      this._now = /* @__PURE__ */ new Date();
    }, 1e3);
  }
  disconnectedCallback() {
    this._clockTimer !== void 0 && (window.clearInterval(this._clockTimer), this._clockTimer = void 0), super.disconnectedCallback();
  }
  render() {
    return g`
      <div class="board">
        <div class="frame frame-outer"></div>
        <div class="frame frame-inner"></div>
        <div class="wordmark-row">
          <span class="rule"></span>
          <span class="d20" aria-hidden="true">
            <span class="d20-numeral">20</span>
          </span>
          <span class="wordmark">NestQuest</span>
          <span class="d20" aria-hidden="true">
            <span class="d20-numeral">20</span>
          </span>
          <span class="rule"></span>
        </div>
        <p class="kicker">The Party · ${R(this._now, this._timeZone())}</p>
        <div class="plates">
          ${this._plates().map((t) => this._renderPlate(t))}
        </div>
        <p class="hint">Tap your crest to open your Quest Log</p>
        <div class="spacer"></div>
        ${this._renderDock()}
      </div>
    `;
  }
  _timeZone() {
    return Ft(this.hass);
  }
  _state(t) {
    const n = this.hass?.states?.[t];
    return n && typeof n == "object" ? n : null;
  }
  _childSlugs() {
    if (!this._config)
      return [];
    const t = this._config.child_order;
    return Array.isArray(t) ? t.filter(
      (e) => typeof e == "string" && e.trim().length > 0
    ).map((e) => e.trim()) : [];
  }
  _plates() {
    return this._childSlugs().map((t) => this._plate(t));
  }
  _plate(t) {
    const e = this._state(`sensor.nestquest_${t}_quests_due_today`), n = this._state(
      `sensor.nestquest_${t}_quests_completed_today`
    ), i = this._state(
      `sensor.nestquest_${t}_completion_pct_today`
    ), r = this._state(
      `binary_sensor.nestquest_${t}_present_today`
    ), a = e?.attributes ?? {}, l = pt(I(e?.state, 0)), o = pt(I(n?.state, 0)), d = i ? I(i.state, Number.NaN) : Number.NaN, h = Number.isFinite(d) ? lt(d) : l > 0 ? lt(o / l * 100) : 0;
    let p = !0;
    const f = a.present;
    typeof f == "boolean" ? p = f : r && (p = String(r.state ?? "").trim().toLowerCase() === "on");
    let u = "";
    const m = a.child_name;
    if (typeof m == "string" && m.trim())
      u = m.trim();
    else {
      const H = r?.attributes?.child_name;
      typeof H == "string" && H.trim() && (u = H.trim());
    }
    u || (u = Qt(t));
    const Z = Vt(
      r?.attributes?.next_present,
      this._timeZone()
    ), bt = Z ? `Returns ${R(Z, this._timeZone())}` : null;
    return {
      slug: t,
      name: u,
      initial: (u.charAt(0) || "?").toUpperCase(),
      present: p,
      completed: o,
      due: l,
      pct: h,
      returns: bt
    };
  }
  _renderPlate(t) {
    return t.present ? g`
        <button
          class="plate"
          type="button"
          aria-label="Open ${t.name}'s Quest Log"
          @click=${() => this._openQuestLog(t.slug)}
        >
          <span class="crest">
            <span class="crest-face">
              <span class="initial">${t.initial}</span>
            </span>
          </span>
          <span class="name">${t.name}</span>
          <span class="pill">
            ${Xt}
            <span>Home today</span>
          </span>
          <span class="progress-line">
            ${t.completed} of ${t.due} quests claimed
          </span>
          <span class="bar">
            <span class="fill" style="width: ${t.pct}%"></span>
          </span>
        </button>
      ` : g`
      <div class="plate away">
        <span class="crest away">
          <span class="crest-face">
            <span class="initial">${t.initial}</span>
          </span>
        </span>
        <span class="name">${t.name}</span>
        <span class="pill away">
          ${Yt}
          <span>On travels</span>
        </span>
        <span class="progress-line">${t.returns ?? "Returns —"}</span>
        <span class="bar"></span>
      </div>
    `;
  }
  _openQuestLog(t) {
    const e = ot(this._config?.quest_log_path);
    e && (window.history.pushState(null, "", `${e.replace(/\/+$/, "")}/${t}`), window.dispatchEvent(new Event("location-changed")));
  }
  _dockWeather() {
    const t = ot(this._config?.weather_entity);
    if (!t)
      return null;
    const e = this._state(t);
    if (!e)
      return null;
    const n = String(e.state ?? "").trim();
    if (!n || n === "unavailable" || n === "unknown")
      return null;
    const i = e.attributes ?? {};
    let r = null, a = null;
    const l = i.forecast;
    if (Array.isArray(l) && l.length > 0) {
      const o = l[0];
      if (o && typeof o == "object") {
        const d = o;
        r = this._optionalNumber(d.temperature), a = this._optionalNumber(d.templow);
      }
    }
    return {
      condition: n,
      temperature: this._optionalNumber(i.temperature),
      high: r,
      low: a
    };
  }
  _optionalNumber(t) {
    if (t == null || t === "")
      return null;
    const e = typeof t == "number" ? t : Number(t);
    return Number.isFinite(e) ? e : null;
  }
  _renderDock() {
    const t = this._dockWeather();
    if (!t)
      return g`
        <div class="dock">
          <span class="date">${R(this._now, this._timeZone())}</span>
          <span class="divider"></span>
          <span class="clock">${Lt(this._now, this._timeZone())}</span>
        </div>
      `;
    const e = Zt(t.condition), n = Kt(t.condition, e), i = t.temperature === null ? c : g`<span class="temp">${Math.round(t.temperature)}°</span>`, r = t.high === null || t.low === null ? null : `${Math.round(t.high)}° / ${Math.round(t.low)}°`;
    return g`
      <div class="dock">
        ${te}
        ${i}
        <span class="divider"></span>
        <span class="condition">
          ${r === null ? e : `${e} · ${r}`}
        </span>
        <span class="divider"></span>
        <span class="condition">${n}</span>
      </div>
    `;
  }
}
customElements.define("nestquest-party-board-card", ee);
V({
  type: "nestquest-party-board-card",
  name: "NestQuest Party Board",
  description: "Kids' attract screen for present and away adventurers."
});
class ne extends v {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 }
  };
  static styles = [$(yt)];
  hass;
  _config;
  setConfig(t) {
    if (!t || typeof t != "object")
      throw new Error("Invalid configuration");
    this._config = t;
  }
  getCardSize() {
    return 8;
  }
  render() {
    return g`<div>NestQuest Quest Log</div>`;
  }
}
customElements.define("nestquest-quest-log-card", ne);
V({
  type: "nestquest-quest-log-card",
  name: "NestQuest Quest Log",
  description: "One child's daily quests, grouped by window."
});
const se = ":host{--nq-brand-blue: #3B3AB8;--nq-brand-purple: #A035CC;--nq-brand-gradient: linear-gradient(135deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-brand-gradient-h: linear-gradient(90deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-a-page: #F4F4F6;--nq-a-surface: #FFFFFF;--nq-a-surface-subtle: #FAFAFA;--nq-a-selected: #EBEBF8;--nq-a-border: #E4E4EA;--nq-a-divider: #EDEDF1;--nq-a-ink: #18181D;--nq-a-ink-secondary: #52525E;--nq-a-ink-tertiary: #70707E;--nq-a-success: #15803D;--nq-a-danger: #DC2626;--nq-a-danger-strong: #B91C1C;--nq-a-danger-bg: #FEE2E2;--nq-a-warning-ink: #92400E;--nq-a-warning-ink-2: #78350F;--nq-a-warning-bg: #FEF3C7;--nq-a-warning-border: rgba(217,119,6,.35);--nq-a-info-bg: #DBEAFE;--nq-a-info-ink: #1E3A8A;--nq-a-info-icon: #1D4ED8;--nq-a-reversal: #7D28A0;--nq-a-font: Nunito, system-ui, sans-serif;--nq-a-size-screen: 24px;--nq-a-size-hero: 32px;--nq-a-size-card-title: 19px;--nq-a-size-stat: 22px;--nq-a-size-row: 13.5px;--nq-a-size-meta: 11px;--nq-a-size-label: 10px;--nq-a-track-label: .1em;--nq-a-density-page-pad: 14px 16px 92px;--nq-a-density-gap: 10px;--nq-a-density-card-pad: 13px;--nq-a-density-row-pad: 11px 13px;--nq-a-density-radius: 8px;--nq-a-density-shadow: none;--nq-a-tabbar-height: 70px;--nq-a-tap-min: 44px;--nq-a-radius-pill: 9999px;--nq-a-radius-sheet: 20px 20px 0 0;--nq-a-sheet-shadow: 0 -8px 28px rgba(9,9,11,.18);--nq-a-progress-height: 6px;--nq-ease-out: cubic-bezier(0, 0, .2, 1);--nq-dur-micro: .12s;--nq-dur-base: .2s;--nq-dur-modal: .35s}";
class ie extends v {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 }
  };
  static styles = [$(se)];
  hass;
  _config;
  setConfig(t) {
    if (!t || typeof t != "object")
      throw new Error("Invalid configuration");
    this._config = t;
  }
  getCardSize() {
    return 8;
  }
  render() {
    return g`<div>NestQuest Admin</div>`;
  }
}
customElements.define("nestquest-admin-card", ie);
V({
  type: "nestquest-admin-card",
  name: "NestQuest Admin",
  description: "Parent phone view for today, tasks, schedule, and history."
});
const re = "/nestquest-static/nestquest-fonts.css";
if (!document.querySelector('link[data-nq-fonts=""]')) {
  const s = document.createElement("link");
  s.rel = "stylesheet", s.href = re, s.dataset.nqFonts = "", document.head.appendChild(s);
}

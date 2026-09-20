const L = globalThis, Y = L.ShadowRoot && (L.ShadyCSS === void 0 || L.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, tt = /* @__PURE__ */ Symbol(), rt = /* @__PURE__ */ new WeakMap();
let Nt = class {
  constructor(t, e, n) {
    if (this._$cssResult$ = !0, n !== tt) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = t, this.t = e;
  }
  get styleSheet() {
    let t = this.o;
    const e = this.t;
    if (Y && t === void 0) {
      const n = e !== void 0 && e.length === 1;
      n && (t = rt.get(e)), t === void 0 && ((this.o = t = new CSSStyleSheet()).replaceSync(this.cssText), n && rt.set(e, t));
    }
    return t;
  }
  toString() {
    return this.cssText;
  }
};
const b = (i) => new Nt(typeof i == "string" ? i : i + "", void 0, tt), Tt = (i, ...t) => {
  const e = i.length === 1 ? i[0] : t.reduce((n, s, r) => n + ((o) => {
    if (o._$cssResult$ === !0) return o.cssText;
    if (typeof o == "number") return o;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + o + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(s) + i[r + 1], i[0]);
  return new Nt(e, i, tt);
}, It = (i, t) => {
  if (Y) i.adoptedStyleSheets = t.map((e) => e instanceof CSSStyleSheet ? e : e.styleSheet);
  else for (const e of t) {
    const n = document.createElement("style"), s = L.litNonce;
    s !== void 0 && n.setAttribute("nonce", s), n.textContent = e.cssText, i.appendChild(n);
  }
}, ot = Y ? (i) => i : (i) => i instanceof CSSStyleSheet ? ((t) => {
  let e = "";
  for (const n of t.cssRules) e += n.cssText;
  return b(e);
})(i) : i;
const { is: Ht, defineProperty: jt, getOwnPropertyDescriptor: Lt, getOwnPropertyNames: Rt, getOwnPropertySymbols: Bt, getPrototypeOf: Ft } = Object, F = globalThis, at = F.trustedTypes, Qt = at ? at.emptyScript : "", Wt = F.reactiveElementPolyfillSupport, U = (i, t) => i, X = { toAttribute(i, t) {
  switch (t) {
    case Boolean:
      i = i ? Qt : null;
      break;
    case Object:
    case Array:
      i = i == null ? i : JSON.stringify(i);
  }
  return i;
}, fromAttribute(i, t) {
  let e = i;
  switch (t) {
    case Boolean:
      e = i !== null;
      break;
    case Number:
      e = i === null ? null : Number(i);
      break;
    case Object:
    case Array:
      try {
        e = JSON.parse(i);
      } catch {
        e = null;
      }
  }
  return e;
} }, Mt = (i, t) => !Ht(i, t), lt = { attribute: !0, type: String, converter: X, reflect: !1, useDefault: !1, hasChanged: Mt };
Symbol.metadata ??= /* @__PURE__ */ Symbol("metadata"), F.litPropertyMetadata ??= /* @__PURE__ */ new WeakMap();
let T = class extends HTMLElement {
  static addInitializer(t) {
    this._$Ei(), (this.l ??= []).push(t);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(t, e = lt) {
    if (e.state && (e.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(t) && ((e = Object.create(e)).wrapped = !0), this.elementProperties.set(t, e), !e.noAccessor) {
      const n = /* @__PURE__ */ Symbol(), s = this.getPropertyDescriptor(t, n, e);
      s !== void 0 && jt(this.prototype, t, s);
    }
  }
  static getPropertyDescriptor(t, e, n) {
    const { get: s, set: r } = Lt(this.prototype, t) ?? { get() {
      return this[e];
    }, set(o) {
      this[e] = o;
    } };
    return { get: s, set(o) {
      const l = s?.call(this);
      r?.call(this, o), this.requestUpdate(t, l, n);
    }, configurable: !0, enumerable: !0 };
  }
  static getPropertyOptions(t) {
    return this.elementProperties.get(t) ?? lt;
  }
  static _$Ei() {
    if (this.hasOwnProperty(U("elementProperties"))) return;
    const t = Ft(this);
    t.finalize(), t.l !== void 0 && (this.l = [...t.l]), this.elementProperties = new Map(t.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(U("finalized"))) return;
    if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(U("properties"))) {
      const e = this.properties, n = [...Rt(e), ...Bt(e)];
      for (const s of n) this.createProperty(s, e[s]);
    }
    const t = this[Symbol.metadata];
    if (t !== null) {
      const e = litPropertyMetadata.get(t);
      if (e !== void 0) for (const [n, s] of e) this.elementProperties.set(n, s);
    }
    this._$Eh = /* @__PURE__ */ new Map();
    for (const [e, n] of this.elementProperties) {
      const s = this._$Eu(e, n);
      s !== void 0 && this._$Eh.set(s, e);
    }
    this.elementStyles = this.finalizeStyles(this.styles);
  }
  static finalizeStyles(t) {
    const e = [];
    if (Array.isArray(t)) {
      const n = new Set(t.flat(1 / 0).reverse());
      for (const s of n) e.unshift(ot(s));
    } else t !== void 0 && e.push(ot(t));
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
    return It(t, this.constructor.elementStyles), t;
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
    const n = this.constructor.elementProperties.get(t), s = this.constructor._$Eu(t, n);
    if (s !== void 0 && n.reflect === !0) {
      const r = (n.converter?.toAttribute !== void 0 ? n.converter : X).toAttribute(e, n.type);
      this._$Em = t, r == null ? this.removeAttribute(s) : this.setAttribute(s, r), this._$Em = null;
    }
  }
  _$AK(t, e) {
    const n = this.constructor, s = n._$Eh.get(t);
    if (s !== void 0 && this._$Em !== s) {
      const r = n.getPropertyOptions(s), o = typeof r.converter == "function" ? { fromAttribute: r.converter } : r.converter?.fromAttribute !== void 0 ? r.converter : X;
      this._$Em = s;
      const l = o.fromAttribute(e, r.type);
      this[s] = l ?? this._$Ej?.get(s) ?? l, this._$Em = null;
    }
  }
  requestUpdate(t, e, n, s = !1, r) {
    if (t !== void 0) {
      const o = this.constructor;
      if (s === !1 && (r = this[t]), n ??= o.getPropertyOptions(t), !((n.hasChanged ?? Mt)(r, e) || n.useDefault && n.reflect && r === this._$Ej?.get(t) && !this.hasAttribute(o._$Eu(t, n)))) return;
      this.C(t, e, n);
    }
    this.isUpdatePending === !1 && (this._$ES = this._$EP());
  }
  C(t, e, { useDefault: n, reflect: s, wrapped: r }, o) {
    n && !(this._$Ej ??= /* @__PURE__ */ new Map()).has(t) && (this._$Ej.set(t, o ?? e ?? this[t]), r !== !0 || o !== void 0) || (this._$AL.has(t) || (this.hasUpdated || n || (e = void 0), this._$AL.set(t, e)), s === !0 && this._$Em !== t && (this._$Eq ??= /* @__PURE__ */ new Set()).add(t));
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
        for (const [s, r] of this._$Ep) this[s] = r;
        this._$Ep = void 0;
      }
      const n = this.constructor.elementProperties;
      if (n.size > 0) for (const [s, r] of n) {
        const { wrapped: o } = r, l = this[s];
        o !== !0 || this._$AL.has(s) || l === void 0 || this.C(s, void 0, r, l);
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
T.elementStyles = [], T.shadowRootOptions = { mode: "open" }, T[U("elementProperties")] = /* @__PURE__ */ new Map(), T[U("finalized")] = /* @__PURE__ */ new Map(), Wt?.({ ReactiveElement: T }), (F.reactiveElementVersions ??= []).push("2.1.2");
const et = globalThis, dt = (i) => i, R = et.trustedTypes, pt = R ? R.createPolicy("lit-html", { createHTML: (i) => i }) : void 0, zt = "$lit$", x = `lit$${Math.random().toFixed(9).slice(2)}$`, Pt = "?" + x, Zt = `<${Pt}>`, S = document, D = () => S.createComment(""), I = (i) => i === null || typeof i != "object" && typeof i != "function", nt = Array.isArray, Vt = (i) => nt(i) || typeof i?.[Symbol.iterator] == "function", W = `[ 	
\f\r]`, P = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, ct = /-->/g, ht = />/g, q = RegExp(`>|${W}(?:([^\\s"'>=/]+)(${W}*=${W}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g"), ut = /'/g, ft = /"/g, Ot = /^(?:script|style|textarea|title)$/i, Kt = (i) => (t, ...e) => ({ _$litType$: i, strings: t, values: e }), g = Kt(1), E = /* @__PURE__ */ Symbol.for("lit-noChange"), m = /* @__PURE__ */ Symbol.for("lit-nothing"), mt = /* @__PURE__ */ new WeakMap(), A = S.createTreeWalker(S, 129);
function Ut(i, t) {
  if (!nt(i) || !i.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return pt !== void 0 ? pt.createHTML(t) : t;
}
const Jt = (i, t) => {
  const e = i.length - 1, n = [];
  let s, r = t === 2 ? "<svg>" : t === 3 ? "<math>" : "", o = P;
  for (let l = 0; l < e; l++) {
    const a = i[l];
    let p, u, d = -1, h = 0;
    for (; h < a.length && (o.lastIndex = h, u = o.exec(a), u !== null); ) h = o.lastIndex, o === P ? u[1] === "!--" ? o = ct : u[1] !== void 0 ? o = ht : u[2] !== void 0 ? (Ot.test(u[2]) && (s = RegExp("</" + u[2], "g")), o = q) : u[3] !== void 0 && (o = q) : o === q ? u[0] === ">" ? (o = s ?? P, d = -1) : u[1] === void 0 ? d = -2 : (d = o.lastIndex - u[2].length, p = u[1], o = u[3] === void 0 ? q : u[3] === '"' ? ft : ut) : o === ft || o === ut ? o = q : o === ct || o === ht ? o = P : (o = q, s = void 0);
    const c = o === q && i[l + 1].startsWith("/>") ? " " : "";
    r += o === P ? a + Zt : d >= 0 ? (n.push(p), a.slice(0, d) + zt + a.slice(d) + x + c) : a + x + (d === -2 ? l : c);
  }
  return [Ut(i, r + (i[e] || "<?>") + (t === 2 ? "</svg>" : t === 3 ? "</math>" : "")), n];
};
class H {
  constructor({ strings: t, _$litType$: e }, n) {
    let s;
    this.parts = [];
    let r = 0, o = 0;
    const l = t.length - 1, a = this.parts, [p, u] = Jt(t, e);
    if (this.el = H.createElement(p, n), A.currentNode = this.el.content, e === 2 || e === 3) {
      const d = this.el.content.firstChild;
      d.replaceWith(...d.childNodes);
    }
    for (; (s = A.nextNode()) !== null && a.length < l; ) {
      if (s.nodeType === 1) {
        if (s.hasAttributes()) for (const d of s.getAttributeNames()) if (d.endsWith(zt)) {
          const h = u[o++], c = s.getAttribute(d).split(x), f = /([.?@])?(.*)/.exec(h);
          a.push({ type: 1, index: r, name: f[2], strings: c, ctor: f[1] === "." ? Xt : f[1] === "?" ? Yt : f[1] === "@" ? te : Q }), s.removeAttribute(d);
        } else d.startsWith(x) && (a.push({ type: 6, index: r }), s.removeAttribute(d));
        if (Ot.test(s.tagName)) {
          const d = s.textContent.split(x), h = d.length - 1;
          if (h > 0) {
            s.textContent = R ? R.emptyScript : "";
            for (let c = 0; c < h; c++) s.append(d[c], D()), A.nextNode(), a.push({ type: 2, index: ++r });
            s.append(d[h], D());
          }
        }
      } else if (s.nodeType === 8) if (s.data === Pt) a.push({ type: 2, index: r });
      else {
        let d = -1;
        for (; (d = s.data.indexOf(x, d + 1)) !== -1; ) a.push({ type: 7, index: r }), d += x.length - 1;
      }
      r++;
    }
  }
  static createElement(t, e) {
    const n = S.createElement("template");
    return n.innerHTML = t, n;
  }
}
function M(i, t, e = i, n) {
  if (t === E) return t;
  let s = n !== void 0 ? e._$Co?.[n] : e._$Cl;
  const r = I(t) ? void 0 : t._$litDirective$;
  return s?.constructor !== r && (s?._$AO?.(!1), r === void 0 ? s = void 0 : (s = new r(i), s._$AT(i, e, n)), n !== void 0 ? (e._$Co ??= [])[n] = s : e._$Cl = s), s !== void 0 && (t = M(i, s._$AS(i, t.values), s, n)), t;
}
class Gt {
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
    const { el: { content: e }, parts: n } = this._$AD, s = (t?.creationScope ?? S).importNode(e, !0);
    A.currentNode = s;
    let r = A.nextNode(), o = 0, l = 0, a = n[0];
    for (; a !== void 0; ) {
      if (o === a.index) {
        let p;
        a.type === 2 ? p = new z(r, r.nextSibling, this, t) : a.type === 1 ? p = new a.ctor(r, a.name, a.strings, this, t) : a.type === 6 && (p = new ee(r, this, t)), this._$AV.push(p), a = n[++l];
      }
      o !== a?.index && (r = A.nextNode(), o++);
    }
    return A.currentNode = S, s;
  }
  p(t) {
    let e = 0;
    for (const n of this._$AV) n !== void 0 && (n.strings !== void 0 ? (n._$AI(t, n, e), e += n.strings.length - 2) : n._$AI(t[e])), e++;
  }
}
class z {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(t, e, n, s) {
    this.type = 2, this._$AH = m, this._$AN = void 0, this._$AA = t, this._$AB = e, this._$AM = n, this.options = s, this._$Cv = s?.isConnected ?? !0;
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
    t = M(this, t, e), I(t) ? t === m || t == null || t === "" ? (this._$AH !== m && this._$AR(), this._$AH = m) : t !== this._$AH && t !== E && this._(t) : t._$litType$ !== void 0 ? this.$(t) : t.nodeType !== void 0 ? this.T(t) : Vt(t) ? this.k(t) : this._(t);
  }
  O(t) {
    return this._$AA.parentNode.insertBefore(t, this._$AB);
  }
  T(t) {
    this._$AH !== t && (this._$AR(), this._$AH = this.O(t));
  }
  _(t) {
    this._$AH !== m && I(this._$AH) ? this._$AA.nextSibling.data = t : this.T(S.createTextNode(t)), this._$AH = t;
  }
  $(t) {
    const { values: e, _$litType$: n } = t, s = typeof n == "number" ? this._$AC(t) : (n.el === void 0 && (n.el = H.createElement(Ut(n.h, n.h[0]), this.options)), n);
    if (this._$AH?._$AD === s) this._$AH.p(e);
    else {
      const r = new Gt(s, this), o = r.u(this.options);
      r.p(e), this.T(o), this._$AH = r;
    }
  }
  _$AC(t) {
    let e = mt.get(t.strings);
    return e === void 0 && mt.set(t.strings, e = new H(t)), e;
  }
  k(t) {
    nt(this._$AH) || (this._$AH = [], this._$AR());
    const e = this._$AH;
    let n, s = 0;
    for (const r of t) s === e.length ? e.push(n = new z(this.O(D()), this.O(D()), this, this.options)) : n = e[s], n._$AI(r), s++;
    s < e.length && (this._$AR(n && n._$AB.nextSibling, s), e.length = s);
  }
  _$AR(t = this._$AA.nextSibling, e) {
    for (this._$AP?.(!1, !0, e); t !== this._$AB; ) {
      const n = dt(t).nextSibling;
      dt(t).remove(), t = n;
    }
  }
  setConnected(t) {
    this._$AM === void 0 && (this._$Cv = t, this._$AP?.(t));
  }
}
class Q {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(t, e, n, s, r) {
    this.type = 1, this._$AH = m, this._$AN = void 0, this.element = t, this.name = e, this._$AM = s, this.options = r, n.length > 2 || n[0] !== "" || n[1] !== "" ? (this._$AH = Array(n.length - 1).fill(new String()), this.strings = n) : this._$AH = m;
  }
  _$AI(t, e = this, n, s) {
    const r = this.strings;
    let o = !1;
    if (r === void 0) t = M(this, t, e, 0), o = !I(t) || t !== this._$AH && t !== E, o && (this._$AH = t);
    else {
      const l = t;
      let a, p;
      for (t = r[0], a = 0; a < r.length - 1; a++) p = M(this, l[n + a], e, a), p === E && (p = this._$AH[a]), o ||= !I(p) || p !== this._$AH[a], p === m ? t = m : t !== m && (t += (p ?? "") + r[a + 1]), this._$AH[a] = p;
    }
    o && !s && this.j(t);
  }
  j(t) {
    t === m ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, t ?? "");
  }
}
class Xt extends Q {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(t) {
    this.element[this.name] = t === m ? void 0 : t;
  }
}
class Yt extends Q {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(t) {
    this.element.toggleAttribute(this.name, !!t && t !== m);
  }
}
class te extends Q {
  constructor(t, e, n, s, r) {
    super(t, e, n, s, r), this.type = 5;
  }
  _$AI(t, e = this) {
    if ((t = M(this, t, e, 0) ?? m) === E) return;
    const n = this._$AH, s = t === m && n !== m || t.capture !== n.capture || t.once !== n.once || t.passive !== n.passive, r = t !== m && (n === m || s);
    s && this.element.removeEventListener(this.name, this, n), r && this.element.addEventListener(this.name, this, t), this._$AH = t;
  }
  handleEvent(t) {
    typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, t) : this._$AH.handleEvent(t);
  }
}
class ee {
  constructor(t, e, n) {
    this.element = t, this.type = 6, this._$AN = void 0, this._$AM = e, this.options = n;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t) {
    M(this, t);
  }
}
const ne = { I: z }, ie = et.litHtmlPolyfillSupport;
ie?.(H, z), (et.litHtmlVersions ??= []).push("3.3.3");
const se = (i, t, e) => {
  const n = e?.renderBefore ?? t;
  let s = n._$litPart$;
  if (s === void 0) {
    const r = e?.renderBefore ?? null;
    n._$litPart$ = s = new z(t.insertBefore(D(), r), r, void 0, e ?? {});
  }
  return s._$AI(i), s;
};
const it = globalThis;
let C = class extends T {
  constructor() {
    super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
  }
  createRenderRoot() {
    const t = super.createRenderRoot();
    return this.renderOptions.renderBefore ??= t.firstChild, t;
  }
  update(t) {
    const e = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t), this._$Do = se(e, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(!0);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(!1);
  }
  render() {
    return E;
  }
};
C._$litElement$ = !0, C.finalized = !0, it.litElementHydrateSupport?.({ LitElement: C });
const re = it.litElementPolyfillSupport;
re?.({ LitElement: C });
(it.litElementVersions ??= []).push("4.2.2");
const Dt = ':host{--nq-p-parchment-top: #f0e4c7;--nq-p-parchment-bottom: #ddcca3;--nq-p-parchment: radial-gradient(ellipse at 25% 10%, rgba(255,255,255,.5), transparent 55%), radial-gradient(ellipse at 85% 90%, rgba(120,86,44,.28), transparent 60%), repeating-linear-gradient(93deg, rgba(150,115,70,.05) 0 2px, transparent 2px 6px), repeating-linear-gradient(2deg, rgba(150,115,70,.04) 0 3px, transparent 3px 7px), linear-gradient(var(--nq-p-parchment-top), var(--nq-p-parchment-bottom));--nq-p-vignette: inset 0 0 200px rgba(80,52,20,.35);--nq-p-card-open: linear-gradient(#fdf7e6, #f2e7c9);--nq-p-card-done: linear-gradient(#f0e8d3, #e6dcc2);--nq-p-card-panel: linear-gradient(#fcf6e6, #f1e6ca);--nq-p-card-border: rgba(120,88,48,.38);--nq-p-panel-border: rgba(92,62,26,.4);--nq-p-card-shadow: 0 3px 0 rgba(120,88,48,.2), inset 0 1px 0 rgba(255,255,255,.7);--nq-p-panel-shadow: 0 6px 0 rgba(92,62,26,.18), inset 0 2px 0 rgba(255,255,255,.7);--nq-p-frame-outer: 2px solid rgba(92,62,26,.45);--nq-p-frame-inner: 1px solid rgba(92,62,26,.28);--nq-p-rule: 2px solid rgba(92,62,26,.35);--nq-p-ink: #2b1f14;--nq-p-ink-secondary: #5c452a;--nq-p-ink-muted: #6f6455;--nq-p-ink-away: #4d4433;--nq-p-ink-late: #8f1526;--nq-brand-blue: #3B3AB8;--nq-brand-purple: #A035CC;--nq-brand-gradient: linear-gradient(135deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-p-icon-tile: var(--nq-brand-gradient);--nq-p-icon-tile-done: rgba(92,62,26,.16);--nq-p-crest: var(--nq-brand-gradient);--nq-p-crest-away: linear-gradient(135deg, #6b6b7a, #7a7286);--nq-p-seal: radial-gradient(circle at 35% 30%, #a8283a, #6d1322);--nq-p-seal-shadow: 0 4px 10px rgba(60,10,20,.4), inset 0 0 0 4px rgba(255,255,255,.14);--nq-p-seal-size: 78px;--nq-p-dock-bg: rgba(43,31,20,.9);--nq-p-dock-ink: #f7efdb;--nq-p-dock-ink-secondary: #d8c9a6;--nq-p-dock-divider: rgba(233,220,189,.3);--nq-p-dock-height: 84px;--nq-p-font-display: "Cinzel Decorative", Cinzel, serif;--nq-p-font-heading: Cinzel, serif;--nq-p-font-body: Nunito, system-ui, sans-serif;--nq-p-size-hero: 86px;--nq-p-size-wordmark: 66px;--nq-p-size-title: 56px;--nq-p-size-name: 48px;--nq-p-size-section: 32px;--nq-p-size-quest: 30px;--nq-p-size-body: 22px;--nq-p-size-label: 21px;--nq-p-track-label: .14em;--nq-p-track-kicker: .3em;--nq-p-quest-min-height: 116px;--nq-p-quest-gap: 24px;--nq-p-quest-pad: 22px;--nq-p-tile-size: 64px;--nq-p-button-height: 72px;--nq-p-button-min-width: 150px;--nq-p-confirm-button: 108px;--nq-p-radius-card: 12px;--nq-p-radius-panel: 20px;--nq-p-radius-pill: 9999px;--nq-p-page-inset: 62px;--nq-p-frame-inset: 26px;--nq-ease-out: cubic-bezier(0, 0, .2, 1);--nq-dur-micro: .12s;--nq-dur-base: .2s;--nq-dur-modal: .35s}';
function st(i) {
  window.customCards = window.customCards ?? [], window.customCards.push(i);
}
const gt = /* @__PURE__ */ new Map();
function B(i, t) {
  const e = `${i ?? "local"}|${JSON.stringify(t)}`, n = gt.get(e);
  if (n)
    return n;
  let s;
  try {
    s = new Intl.DateTimeFormat("en-US", {
      ...t,
      ...i ? { timeZone: i } : {}
    });
  } catch {
    s = new Intl.DateTimeFormat("en-US", t);
  }
  return gt.set(e, s), s;
}
function oe(i) {
  const t = i?.config;
  if (!t || typeof t != "object")
    return;
  const e = t.time_zone;
  return typeof e == "string" && e.trim() ? e.trim() : void 0;
}
function Z(i, t) {
  return `${B(t, { weekday: "long" }).format(i)}, ${B(t, { month: "short", day: "numeric" }).format(i)}`;
}
function ae(i, t) {
  return B(t, {
    hour: "numeric",
    minute: "2-digit",
    hour12: !0
  }).format(i);
}
const le = {
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
}, de = {
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
function _t(i) {
  return typeof i == "string" ? i.trim() : "";
}
function V(i, t) {
  if (i == null || i === "")
    return t;
  const e = typeof i == "number" ? i : Number(i);
  return Number.isFinite(e) ? e : t;
}
function yt(i) {
  return Number.isFinite(i) ? Math.min(100, Math.max(0, i)) : 0;
}
function bt(i) {
  return Math.max(0, Math.round(i));
}
function pe(i) {
  return i.split(/[-_]+/).filter(Boolean).map((t) => t.charAt(0).toUpperCase() + t.slice(1)).join(" ");
}
function ce(i, t) {
  const e = B(t, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23"
  }).formatToParts(new Date(i)), n = (r) => {
    const o = e.find((l) => l.type === r);
    return o ? Number(o.value) : Number.NaN;
  }, s = Date.UTC(
    n("year"),
    n("month") - 1,
    n("day"),
    n("hour"),
    n("minute"),
    n("second")
  );
  return Number.isFinite(s) ? s - i : 0;
}
function he(i, t) {
  if (typeof i != "string")
    return null;
  const e = i.split("-");
  if (e.length !== 3)
    return null;
  const [n, s, r] = e.map((a) => Number(a));
  if (!n || !s || !r)
    return null;
  if (!t) {
    const a = new Date(n, s - 1, r);
    return Number.isNaN(a.getTime()) ? null : a;
  }
  const o = Date.UTC(n, s - 1, r), l = new Date(o - ce(o, t));
  return Number.isNaN(l.getTime()) ? null : l;
}
function ue(i) {
  const t = le[i];
  return t || i.charAt(0).toUpperCase() + i.slice(1);
}
function fe(i, t) {
  return de[i] ?? t;
}
const vt = "polygon(0 0, 100% 0, 100% 62%, 50% 100%, 0 62%)", me = "polygon(50% 0, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)", ge = Tt`
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
    clip-path: ${b(me)};
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
    clip-path: ${b(vt)};
    background: rgba(255, 255, 255, 0.22);
  }

  .crest-face {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-bottom: 70px;
    clip-path: ${b(vt)};
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
`, _e = g`<svg
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
</svg>`, ye = g`<svg
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
</svg>`, be = g`<svg
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
class ve extends C {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 },
    _now: { state: !0 }
  };
  static styles = [b(Dt), ge];
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
    return 22;
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
        <p class="kicker">The Party · ${Z(this._now, this._timeZone())}</p>
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
    return oe(this.hass);
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
    ), s = this._state(
      `sensor.nestquest_${t}_completion_pct_today`
    ), r = this._state(
      `binary_sensor.nestquest_${t}_present_today`
    ), o = e?.attributes ?? {}, l = bt(V(e?.state, 0)), a = bt(V(n?.state, 0)), p = s ? V(s.state, Number.NaN) : Number.NaN, u = Number.isFinite(p) ? yt(p) : l > 0 ? yt(a / l * 100) : 0;
    let d = !0;
    const h = o.present;
    typeof h == "boolean" ? d = h : r && (d = String(r.state ?? "").trim().toLowerCase() === "on");
    let c = "";
    const f = o.child_name;
    if (typeof f == "string" && f.trim())
      c = f.trim();
    else {
      const N = r?.attributes?.child_name;
      typeof N == "string" && N.trim() && (c = N.trim());
    }
    c || (c = pe(t));
    const _ = he(
      r?.attributes?.next_present,
      this._timeZone()
    ), v = _ ? `Returns ${Z(_, this._timeZone())}` : null;
    return {
      slug: t,
      name: c,
      initial: (c.charAt(0) || "?").toUpperCase(),
      present: d,
      completed: a,
      due: l,
      pct: u,
      returns: v
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
            ${_e}
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
          ${ye}
          <span>On travels</span>
        </span>
        <span class="progress-line">${t.returns ?? "Returns —"}</span>
        <span class="bar"></span>
      </div>
    `;
  }
  _openQuestLog(t) {
    const e = _t(this._config?.quest_log_path);
    e && (window.history.pushState(null, "", `${e.replace(/\/+$/, "")}/${t}`), window.dispatchEvent(new Event("location-changed")));
  }
  _dockWeather() {
    const t = _t(this._config?.weather_entity);
    if (!t)
      return null;
    const e = this._state(t);
    if (!e)
      return null;
    const n = String(e.state ?? "").trim();
    if (!n || n === "unavailable" || n === "unknown")
      return null;
    const s = e.attributes ?? {};
    let r = null, o = null;
    const l = s.forecast;
    if (Array.isArray(l) && l.length > 0) {
      const a = l[0];
      if (a && typeof a == "object") {
        const p = a;
        r = this._optionalNumber(p.temperature), o = this._optionalNumber(p.templow);
      }
    }
    return {
      condition: n,
      temperature: this._optionalNumber(s.temperature),
      high: r,
      low: o
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
          <span class="date">${Z(this._now, this._timeZone())}</span>
          <span class="divider"></span>
          <span class="clock">${ae(this._now, this._timeZone())}</span>
        </div>
      `;
    const e = ue(t.condition), n = fe(t.condition, e), s = t.temperature === null ? m : g`<span class="temp">${Math.round(t.temperature)}°</span>`, r = t.high === null || t.low === null ? null : `${Math.round(t.high)}° / ${Math.round(t.low)}°`;
    return g`
      <div class="dock">
        ${be}
        ${s}
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
customElements.define("nestquest-party-board-card", ve);
st({
  type: "nestquest-party-board-card",
  name: "NestQuest Party Board",
  description: "Kids' attract screen for present and away adventurers."
});
const $e = { CHILD: 2 }, xe = (i) => (...t) => ({ _$litDirective$: i, values: t });
let qe = class {
  constructor(t) {
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AT(t, e, n) {
    this._$Ct = t, this._$AM = e, this._$Ci = n;
  }
  _$AS(t, e) {
    return this.update(t, e);
  }
  update(t, e) {
    return this.render(...e);
  }
};
const { I: we } = ne, $t = (i) => i, xt = () => document.createComment(""), O = (i, t, e) => {
  const n = i._$AA.parentNode, s = t === void 0 ? i._$AB : t._$AA;
  if (e === void 0) {
    const r = n.insertBefore(xt(), s), o = n.insertBefore(xt(), s);
    e = new we(r, o, i, i.options);
  } else {
    const r = e._$AB.nextSibling, o = e._$AM, l = o !== i;
    if (l) {
      let a;
      e._$AQ?.(i), e._$AM = i, e._$AP !== void 0 && (a = i._$AU) !== o._$AU && e._$AP(a);
    }
    if (r !== s || l) {
      let a = e._$AA;
      for (; a !== r; ) {
        const p = $t(a).nextSibling;
        $t(n).insertBefore(a, s), a = p;
      }
    }
  }
  return e;
}, w = (i, t, e = i) => (i._$AI(t, e), i), ke = {}, Ae = (i, t = ke) => i._$AH = t, Ce = (i) => i._$AH, K = (i) => {
  i._$AR(), i._$AA.remove();
};
const qt = (i, t, e) => {
  const n = /* @__PURE__ */ new Map();
  for (let s = t; s <= e; s++) n.set(i[s], s);
  return n;
}, wt = xe(class extends qe {
  constructor(i) {
    if (super(i), i.type !== $e.CHILD) throw Error("repeat() can only be used in text expressions");
  }
  dt(i, t, e) {
    let n;
    e === void 0 ? e = t : t !== void 0 && (n = t);
    const s = [], r = [];
    let o = 0;
    for (const l of i) s[o] = n ? n(l, o) : o, r[o] = e(l, o), o++;
    return { values: r, keys: s };
  }
  render(i, t, e) {
    return this.dt(i, t, e).values;
  }
  update(i, [t, e, n]) {
    const s = Ce(i), { values: r, keys: o } = this.dt(t, e, n);
    if (!Array.isArray(s)) return this.ut = o, r;
    const l = this.ut ??= [], a = [];
    let p, u, d = 0, h = s.length - 1, c = 0, f = r.length - 1;
    for (; d <= h && c <= f; ) if (s[d] === null) d++;
    else if (s[h] === null) h--;
    else if (l[d] === o[c]) a[c] = w(s[d], r[c]), d++, c++;
    else if (l[h] === o[f]) a[f] = w(s[h], r[f]), h--, f--;
    else if (l[d] === o[f]) a[f] = w(s[d], r[f]), O(i, a[f + 1], s[d]), d++, f--;
    else if (l[h] === o[c]) a[c] = w(s[h], r[c]), O(i, s[d], s[h]), h--, c++;
    else if (p === void 0 && (p = qt(o, c, f), u = qt(l, d, h)), p.has(l[d])) if (p.has(l[h])) {
      const _ = u.get(o[c]), v = _ !== void 0 ? s[_] : null;
      if (v === null) {
        const N = O(i, s[d]);
        w(N, r[c]), a[c] = N;
      } else a[c] = w(v, r[c]), O(i, s[d], v), s[_] = null;
      c++;
    } else K(s[h]), h--;
    else K(s[d]), d++;
    for (; c <= f; ) {
      const _ = O(i, a[f + 1]);
      w(_, r[c]), a[c++] = _;
    }
    for (; d <= h; ) {
      const _ = s[d++];
      _ !== null && K(_);
    }
    return this.ut = o, Ae(i, a), E;
  }
}), kt = /* @__PURE__ */ new Map();
function j(i, t) {
  const e = `${i ?? "local"}|${JSON.stringify(t)}`, n = kt.get(e);
  if (n)
    return n;
  let s;
  try {
    s = new Intl.DateTimeFormat("en-US", {
      ...t,
      ...i ? { timeZone: i } : {}
    });
  } catch {
    s = new Intl.DateTimeFormat("en-US", t);
  }
  return kt.set(e, s), s;
}
function Se(i) {
  const t = i?.config;
  if (!t || typeof t != "object")
    return;
  const e = t.time_zone;
  return typeof e == "string" && e.trim() ? e.trim() : void 0;
}
function Ee(i, t) {
  return `${j(t, { weekday: "long" }).format(i)}, ${j(t, { month: "short", day: "numeric" }).format(i)}`;
}
function Ne(i, t) {
  return j(t, { weekday: "long" }).format(i);
}
function Te(i, t) {
  const e = new Date(i);
  return Number.isNaN(e.getTime()) ? "" : j(t, {
    hour: "numeric",
    minute: "2-digit",
    hour12: !0
  }).format(e);
}
function Me(i) {
  if (!i)
    return null;
  const t = /^(\d{1,2}):(\d{2})$/.exec(i.trim());
  if (!t)
    return null;
  const e = Number(t[1]);
  if (e > 23)
    return null;
  const n = e >= 12 ? "PM" : "AM";
  return `${e % 12 === 0 ? 12 : e % 12}:${t[2]} ${n}`;
}
function k(i) {
  return typeof i == "string" ? i.trim() : "";
}
function y(i, t) {
  if (i == null || i === "")
    return t;
  const e = typeof i == "number" ? i : Number(i);
  return Number.isFinite(e) ? e : t;
}
function $(i) {
  return Math.max(0, Math.round(i));
}
function At(i) {
  return i.split(/[-_]+/).filter(Boolean).map((t) => t.charAt(0).toUpperCase() + t.slice(1)).join(" ");
}
function ze(i, t) {
  const e = j(t, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23"
  }).formatToParts(new Date(i)), n = (r) => {
    const o = e.find((l) => l.type === r);
    return o ? Number(o.value) : Number.NaN;
  }, s = Date.UTC(
    n("year"),
    n("month") - 1,
    n("day"),
    n("hour"),
    n("minute"),
    n("second")
  );
  return Number.isFinite(s) ? s - i : 0;
}
function Pe(i, t) {
  if (typeof i != "string")
    return null;
  const e = i.split("-");
  if (e.length !== 3)
    return null;
  const [n, s, r] = e.map((a) => Number(a));
  if (!n || !s || !r)
    return null;
  if (!t) {
    const a = new Date(n, s - 1, r);
    return Number.isNaN(a.getTime()) ? null : a;
  }
  const o = Date.UTC(n, s - 1, r), l = new Date(o - ze(o, t));
  return Number.isNaN(l.getTime()) ? null : l;
}
function Oe() {
  const i = window.location.pathname.split("/").filter(Boolean);
  return i.length > 0 ? i[i.length - 1].toLowerCase() : "";
}
function Ue(i) {
  if (!i || typeof i != "object")
    return null;
  const t = i, e = k(t.state).toLowerCase();
  if (e !== "open" && e !== "completed")
    return null;
  const n = y(t.id, 0);
  return n ? {
    id: n,
    title: k(t.title) || "Quest",
    icon: k(t.icon) || null,
    window: k(t.window).toLowerCase(),
    due_time: k(t.due_time) || null,
    state: e,
    overdue: t.overdue === !0,
    completed_at: k(t.completed_at) || null
  } : null;
}
const Ct = "polygon(0 0, 100% 0, 100% 62%, 50% 100%, 0 62%)", De = "polygon(50% 0, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)", St = [-9, 6, -4], Ie = Tt`
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

  .header {
    position: absolute;
    top: 56px;
    left: var(--nq-p-page-inset);
    right: var(--nq-p-page-inset);
    display: flex;
    align-items: center;
    gap: 28px;
  }

  .crest {
    position: relative;
    flex: none;
    width: 96px;
    height: 110px;
    padding: 3px;
    clip-path: ${b(Ct)};
    background: rgba(255, 255, 255, 0.22);
  }

  .crest-face {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-bottom: 32px;
    clip-path: ${b(Ct)};
    background: var(--nq-p-crest);
  }

  .crest .initial {
    font-family: var(--nq-p-font-display);
    font-size: 44px;
    font-weight: 700;
    line-height: 1;
    color: #ffffff;
  }

  .titles {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }

  .title {
    margin: 0;
    font-family: var(--nq-p-font-display);
    font-size: var(--nq-p-size-title);
    font-weight: 700;
    line-height: 1.1;
    color: var(--nq-p-ink);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sub {
    margin: 0;
    font-family: var(--nq-p-font-heading);
    font-size: 20px;
    font-weight: 600;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .remaining {
    margin-left: auto;
    flex: none;
    display: flex;
    align-items: center;
    gap: 20px;
    padding: 18px 28px;
    border: 2px solid var(--nq-p-panel-border);
    border-radius: 14px;
    background: var(--nq-p-card-panel);
    box-shadow: var(--nq-p-panel-shadow);
  }

  .d20 {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    clip-path: ${b(De)};
    background: var(--nq-brand-gradient);
  }

  .d20-numeral {
    font-family: var(--nq-p-font-heading);
    font-size: 19px;
    font-weight: 700;
    line-height: 1;
    color: #ffffff;
  }

  .remaining-text {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .remaining-count {
    font-family: var(--nq-p-font-heading);
    font-size: 28px;
    font-weight: 700;
    line-height: 1.1;
    color: var(--nq-p-ink);
  }

  .party-line {
    font-family: var(--nq-p-font-body);
    font-size: var(--nq-p-size-body);
    font-weight: 600;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .columns {
    position: absolute;
    top: 236px;
    left: var(--nq-p-page-inset);
    right: var(--nq-p-page-inset);
    bottom: 130px;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 34px;
  }

  .column {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .column-head {
    flex: none;
    display: flex;
    align-items: center;
    gap: 14px;
    padding-bottom: 14px;
    border-bottom: var(--nq-p-rule);
  }

  .column-head svg {
    flex: none;
    width: 34px;
    height: 34px;
    color: var(--nq-p-ink-secondary);
  }

  .column-names {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .column-name {
    font-family: var(--nq-p-font-heading);
    font-size: var(--nq-p-size-section);
    font-weight: 700;
    line-height: 1.1;
    color: var(--nq-p-ink);
  }

  .column-range {
    font-family: var(--nq-p-font-heading);
    font-size: var(--nq-p-size-label);
    font-weight: 600;
    letter-spacing: var(--nq-p-track-label);
    text-transform: uppercase;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .column-count {
    margin-left: auto;
    flex: none;
    font-family: var(--nq-p-font-heading);
    font-size: 26px;
    font-weight: 700;
    line-height: 1.1;
    color: var(--nq-p-ink-secondary);
  }

  .stack {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    overflow: visible;
    gap: var(--nq-p-quest-gap);
    margin-top: 22px;
  }

  .quest {
    position: relative;
    display: flex;
    align-items: center;
    gap: 22px;
    min-height: var(--nq-p-quest-min-height);
    padding: var(--nq-p-quest-pad);
    border: 1px solid var(--nq-p-card-border);
    border-radius: var(--nq-p-radius-card);
    background: var(--nq-p-card-open);
    box-shadow: var(--nq-p-card-shadow);
    -webkit-tap-highlight-color: transparent;
    transition: transform var(--nq-dur-micro) var(--nq-ease-out);
  }

  .quest.tappable {
    cursor: pointer;
  }

  .quest.tappable:active {
    transform: scale(0.98);
  }

  .quest.sealed {
    background: var(--nq-p-card-done);
    opacity: 0.82;
    box-shadow: none;
  }

  .tile {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--nq-p-tile-size);
    height: var(--nq-p-tile-size);
    border-radius: 10px;
    background: var(--nq-p-icon-tile);
    color: #ffffff;
  }

  .tile svg {
    width: 34px;
    height: 34px;
  }

  .sealed .tile {
    background: var(--nq-p-icon-tile-done);
    color: var(--nq-p-ink-secondary);
  }

  .quest .body {
    flex: 1 1 0;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .quest .quest-title {
    font-family: var(--nq-p-font-heading);
    font-size: var(--nq-p-size-quest);
    font-weight: 700;
    line-height: 1.15;
    color: var(--nq-p-ink);
    overflow-wrap: anywhere;
  }

  .sealed .quest-title {
    color: var(--nq-p-ink-muted);
    text-decoration: line-through;
  }

  .quest .meta {
    font-family: var(--nq-p-font-body);
    font-size: var(--nq-p-size-body);
    font-weight: 600;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .quest .meta.late {
    font-family: var(--nq-p-font-heading);
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--nq-p-ink-late);
  }

  button.complete {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    height: var(--nq-p-button-height);
    min-width: var(--nq-p-button-min-width);
    border: none;
    border-radius: 10px;
    background: var(--nq-brand-gradient);
    color: #ffffff;
    font-family: var(--nq-p-font-heading);
    font-size: 24px;
    font-weight: 700;
    line-height: 1;
    box-shadow: 0 3px 0 rgba(40, 20, 60, 0.35);
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    transition: transform var(--nq-dur-micro) var(--nq-ease-out);
  }

  button.complete:active {
    transform: scale(0.98);
  }

  button.complete svg {
    width: 30px;
    height: 30px;
  }

  button:focus-visible {
    outline: 3px solid var(--nq-brand-purple);
    outline-offset: 4px;
  }

  .seal {
    position: absolute;
    right: 16px;
    top: -12px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--nq-p-seal-size);
    height: var(--nq-p-seal-size);
    border-radius: var(--nq-p-radius-pill);
    background: var(--nq-p-seal);
    box-shadow: var(--nq-p-seal-shadow);
    color: rgba(255, 235, 235, 0.95);
    transform: rotate(var(--seal-rot, 0deg));
    animation: seal-in var(--nq-dur-base) var(--nq-ease-out);
    pointer-events: none;
  }

  .seal svg {
    width: 38px;
    height: 38px;
  }

  @keyframes seal-in {
    from {
      opacity: 0;
      transform: scale(1.15) rotate(var(--seal-rot, 0deg));
    }
    to {
      opacity: 1;
      transform: scale(1) rotate(var(--seal-rot, 0deg));
    }
  }

  .rollup {
    border: 2px dashed var(--nq-p-panel-border);
    border-radius: 14px;
    padding: 16px 22px;
  }

  .rollup-label {
    display: block;
    font-family: var(--nq-p-font-heading);
    font-size: 18px;
    font-weight: 600;
    letter-spacing: var(--nq-p-track-label);
    text-transform: uppercase;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .rollup-body {
    margin: 6px 0 0;
    font-family: var(--nq-p-font-body);
    font-size: 23px;
    font-weight: 600;
    line-height: 1.35;
    color: var(--nq-p-ink-secondary);
  }

  .scrim {
    position: absolute;
    inset: 0;
    z-index: 10;
    background: rgba(30, 20, 10, 0.62);
  }

  .dialog {
    position: absolute;
    top: 196px;
    left: 460px;
    width: 1000px;
    border: 3px solid rgba(92, 62, 26, 0.5);
    border-radius: 20px;
    background: var(--nq-p-card-panel);
    box-shadow: 0 26px 60px rgba(20, 10, 0, 0.5);
    padding: 64px 68px 56px;
    animation: dialog-in var(--nq-dur-modal) var(--nq-ease-out);
  }

  @keyframes dialog-in {
    from {
      opacity: 0;
      transform: scale(0.96);
    }
    to {
      opacity: 1;
      transform: scale(1);
    }
  }

  .dialog-header {
    display: flex;
    align-items: center;
    gap: 24px;
  }

  .dialog-tile {
    flex: none;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 104px;
    height: 104px;
    border-radius: 12px;
    background: var(--nq-p-icon-tile);
    color: #ffffff;
  }

  .dialog-tile svg {
    width: 56px;
    height: 56px;
  }

  .dialog-titles {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }

  .dialog-kicker {
    font-family: var(--nq-p-font-heading);
    font-size: var(--nq-p-size-label);
    font-weight: 600;
    letter-spacing: 0.24em;
    text-transform: uppercase;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .dialog-quest-title {
    font-family: var(--nq-p-font-display);
    font-size: 58px;
    font-weight: 700;
    line-height: 1.1;
    color: var(--nq-p-ink);
    overflow-wrap: anywhere;
  }

  .dialog-body {
    margin: 28px 0 0;
    font-family: var(--nq-p-font-body);
    font-size: 32px;
    font-weight: 600;
    line-height: 1.35;
    color: #3f2f1c;
  }

  .dialog-buttons {
    display: flex;
    gap: 24px;
    margin-top: 40px;
  }

  button.confirm-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 12px;
    height: var(--nq-p-confirm-button);
    border-radius: 10px;
    font-family: var(--nq-p-font-heading);
    font-weight: 700;
    line-height: 1;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    transition: transform var(--nq-dur-micro) var(--nq-ease-out);
  }

  button.confirm-button:active {
    transform: scale(0.98);
  }

  button.not-yet {
    flex: 1;
    border: 2px solid rgba(92, 62, 26, 0.5);
    background: rgba(92, 62, 26, 0.1);
    color: var(--nq-p-ink);
    font-size: 30px;
  }

  button.not-yet svg {
    width: 34px;
    height: 34px;
  }

  button.do-complete {
    flex: 2;
    border: none;
    background: var(--nq-brand-gradient);
    color: #ffffff;
    font-size: 32px;
  }

  button.do-complete svg {
    width: 38px;
    height: 38px;
  }
`, J = g`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M20 6 9 17l-5-5"></path>
</svg>`, He = g`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M18 6 6 18"></path>
  <path d="m6 6 12 12"></path>
</svg>`, G = g`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <polygon
    points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26"
  ></polygon>
</svg>`, je = g`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M12 2v8"></path>
  <path d="m4.93 10.93 1.41 1.41"></path>
  <path d="M2 18h2"></path>
  <path d="M20 18h2"></path>
  <path d="m19.07 10.93-1.41 1.41"></path>
  <path d="M22 22H2"></path>
  <path d="m8 6 4-4 4 4"></path>
  <path d="M16 18a4 4 0 0 0-8 0"></path>
</svg>`, Le = g`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <circle cx="12" cy="12" r="4"></circle>
  <path d="M12 2v2"></path>
  <path d="M12 20v2"></path>
  <path d="m4.93 4.93 1.41 1.41"></path>
  <path d="m17.66 17.66 1.41 1.41"></path>
  <path d="M2 12h2"></path>
  <path d="M20 12h2"></path>
  <path d="m6.34 17.66-1.41 1.41"></path>
  <path d="m19.07 4.93-1.41 1.41"></path>
</svg>`, Re = g`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path>
</svg>`, Et = [
  { key: "morning", name: "Morning", range: "Until 11:59 AM", icon: je },
  { key: "afternoon", name: "Afternoon", range: "12:00–5:00 PM", icon: Le },
  { key: "evening", name: "Evening", range: "5:00–9:00 PM", icon: Re }
];
class Be extends C {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 },
    _now: { state: !0 },
    _confirm: { state: !0 }
  };
  static styles = [b(Dt), Ie];
  hass;
  _config;
  _now = /* @__PURE__ */ new Date();
  _confirm = null;
  _clockTimer;
  _idleTimer;
  _confirmTimer;
  setConfig(t) {
    if (!t || typeof t != "object")
      throw new Error("Invalid configuration");
    this._config = t;
  }
  getCardSize() {
    return 22;
  }
  connectedCallback() {
    super.connectedCallback(), this._now = /* @__PURE__ */ new Date(), this._clockTimer = window.setInterval(() => {
      this._now = /* @__PURE__ */ new Date();
    }, 6e4), window.addEventListener("pointerdown", this._onActivity, !0), window.addEventListener("touchstart", this._onActivity, !0), window.addEventListener("keydown", this._onActivity, !0), this._armIdle();
  }
  disconnectedCallback() {
    this._stopClock(), this._clearIdle(), this._clearConfirmTimer(), window.removeEventListener("pointerdown", this._onActivity, !0), window.removeEventListener("touchstart", this._onActivity, !0), window.removeEventListener("keydown", this._onActivity, !0), super.disconnectedCallback();
  }
  render() {
    return g`
      <div class="board">
        <div class="frame frame-outer"></div>
        <div class="frame frame-inner"></div>
        ${this._renderHeader()}
        <div class="columns">
          ${Et.map((t) => this._renderColumn(t))}
        </div>
        ${this._renderConfirm()}
      </div>
    `;
  }
  _timeZone() {
    return Se(this.hass);
  }
  _state(t) {
    const n = this.hass?.states?.[t];
    return n && typeof n == "object" ? n : null;
  }
  _childSlug() {
    return Oe();
  }
  _boardPath() {
    return k(this._config?.board_path).replace(/\/+$/, "");
  }
  _idleSeconds() {
    const t = y(this._config?.idle_return_seconds, 40);
    return t > 0 ? t : 40;
  }
  _confirmSeconds() {
    const t = y(this._config?.confirm_timeout_seconds, 15);
    return t > 0 ? t : 15;
  }
  _childName(t) {
    if (!t)
      return null;
    const e = this._state(`sensor.nestquest_${t}_quests_due_today`)?.attributes?.child_name;
    return typeof e == "string" && e.trim() ? e.trim() : null;
  }
  _childCounts(t) {
    const e = this._state(`sensor.nestquest_${t}_quests_due_today`), n = this._state(
      `sensor.nestquest_${t}_quests_completed_today`
    ), s = $(y(e?.state, 0)), r = $(y(n?.state, 0));
    return { due: s, completed: r };
  }
  _instances() {
    const t = this._childSlug();
    if (!t)
      return [];
    const e = this._state(`sensor.nestquest_${t}_quests_due_today`)?.attributes?.instances;
    return Array.isArray(e) ? e.map(Ue).filter((n) => n !== null) : [];
  }
  _remaining() {
    const t = this._childSlug();
    if (!t)
      return 0;
    const e = this._state(
      `sensor.nestquest_${t}_quests_remaining_today`
    );
    if (e)
      return $(y(e.state, 0));
    const { due: n, completed: s } = this._childCounts(t);
    return $(n - s);
  }
  _partyCounts() {
    const t = this._state(
      "sensor.nestquest_household_quests_due_today"
    ), e = this._state(
      "sensor.nestquest_household_quests_completed_today"
    );
    if (t || e)
      return {
        completed: $(y(e?.state, 0)),
        due: $(y(t?.state, 0))
      };
    const n = this._childSlug(), { due: s, completed: r } = this._childCounts(n);
    return { completed: r, due: s };
  }
  _otherChildren() {
    const t = this.hass?.states;
    if (!t)
      return [];
    const e = this._childSlug(), n = this._timeZone(), s = [];
    for (const r of Object.keys(t)) {
      const o = /^sensor\.nestquest_(.+)_quests_due_today$/.exec(r);
      if (!o || o[1] === "household" || o[1] === e)
        continue;
      const l = o[1], a = t[r]?.attributes ?? {};
      let p = "";
      typeof a.child_name == "string" && a.child_name.trim() ? p = a.child_name.trim() : p = At(l);
      let u = !0;
      if (typeof a.present == "boolean")
        u = a.present;
      else {
        const _ = this._state(
          `binary_sensor.nestquest_${l}_present_today`
        );
        u = _ === null || String(_.state ?? "").trim().toLowerCase() !== "off";
      }
      const d = this._state(
        `sensor.nestquest_${l}_quests_completed_today`
      ), h = $(y(t[r]?.state, 0)), c = $(y(d?.state, 0));
      let f = null;
      if (!u) {
        const _ = this._state(
          `binary_sensor.nestquest_${l}_present_today`
        ), v = Pe(
          _?.attributes?.next_present,
          n
        );
        f = v ? Ne(v, n) : null;
      }
      s.push({
        slug: l,
        name: p,
        present: u,
        due: h,
        completed: c,
        returnsWeekday: f
      });
    }
    return s.sort((r, o) => r.name.localeCompare(o.name));
  }
  _renderHeader() {
    const t = this._childSlug(), n = this._childName(t) ?? (t ? At(t) : null), { due: s, completed: r } = this._childCounts(t), o = this._remaining(), l = this._partyCounts(), a = n ? `${n}'s Quest Log` : "Quest Log", p = (n?.charAt(0) || "?").toUpperCase();
    return g`
      <header class="header">
        <span class="crest" aria-hidden="true">
          <span class="crest-face">
            <span class="initial">${p}</span>
          </span>
        </span>
        <div class="titles">
          <h1 class="title">${a}</h1>
          <p class="sub">
            ${Ee(this._now, this._timeZone())} · ${r} of ${s}
            claimed
          </p>
        </div>
        <div class="remaining">
          <span class="d20" aria-hidden="true">
            <span class="d20-numeral">${o}</span>
          </span>
          <div class="remaining-text">
            <span class="remaining-count">
              ${o} quest${o === 1 ? "" : "s"} left
            </span>
            <span class="party-line">
              Party progress · ${l.completed} of ${l.due} today
            </span>
          </div>
        </div>
      </header>
    `;
  }
  _renderColumn(t) {
    const e = this._instances().filter(
      (l) => l.window === t.key
    ), n = e.filter((l) => l.state === "open").sort(
      (l, a) => (l.due_time ?? "99:99").localeCompare(a.due_time ?? "99:99")
    ), s = e.filter(
      (l) => l.state === "completed"
    ), r = e.length;
    let o = m;
    if (r > 0) {
      const a = Math.min(
        24,
        Math.max(8, Math.floor((644 - r * 72) / Math.max(r - 1, 1)))
      ), p = Math.min(
        116,
        Math.max(72, Math.floor((644 - (r - 1) * a) / r))
      );
      let u = `--nq-p-quest-gap: ${a}px; --nq-p-quest-min-height: ${p}px`;
      if (r >= 5) {
        const d = Math.max(0, Math.min(22, Math.floor((p - 74) / 2))), h = Math.max(44, Math.min(64, p - 2 * d - 2));
        u += `; --nq-p-quest-pad: ${d}px; --nq-p-tile-size: ${h}px`;
      }
      o = u;
    }
    return g`
      <section
        class="column"
        aria-label="${t.name} quests"
        style=${o}
      >
        <div class="column-head">
          ${t.icon}
          <div class="column-names">
            <span class="column-name">${t.name}</span>
            <span class="column-range">${t.range}</span>
          </div>
          <span class="column-count">${s.length}/${e.length}</span>
        </div>
        <div class="stack">
          ${wt(
      n,
      (l) => l.id,
      (l) => this._renderQuest(l, !1, 0)
    )}
          ${wt(
      s,
      (l) => l.id,
      (l, a) => this._renderQuest(l, !0, a)
    )}
          ${t.key === "afternoon" ? this._renderRollup() : m}
        </div>
      </section>
    `;
  }
  _renderQuest(t, e, n) {
    if (e) {
      const o = St[n % St.length], l = t.completed_at ? Te(t.completed_at, this._timeZone()) : "";
      return g`
        <div class="quest sealed" data-instance-id=${t.id}>
          <span class="tile" aria-hidden="true">${G}</span>
          <div class="body">
            <span class="quest-title">${t.title}</span>
            <span class="meta">
              ${l ? `Claimed ${l}` : "Claimed"}
            </span>
          </div>
          <span
            class="seal"
            aria-hidden="true"
            style="--seal-rot: ${o}deg"
          >
            ${J}
          </span>
        </div>
      `;
    }
    const s = Me(t.due_time), r = t.overdue ? {
      text: s ? `Overdue · due ${s}` : "Overdue",
      late: !0
    } : {
      text: s ? `Due by ${s}` : "Due today",
      late: !1
    };
    return g`
      <div
        class="quest tappable"
        role="button"
        tabindex="0"
        data-instance-id=${t.id}
        aria-label="Complete ${t.title}"
        @click=${() => this._openConfirm(t.id)}
        @keydown=${(o) => {
      (o.key === "Enter" || o.key === " ") && (o.preventDefault(), this._openConfirm(t.id));
    }}
      >
        <span class="tile" aria-hidden="true">${G}</span>
        <div class="body">
          <span class="quest-title">${t.title}</span>
          <span class="meta ${r.late ? "late" : m}">${r.text}</span>
        </div>
        <button
          class="complete"
          type="button"
          @click=${() => this._openConfirm(t.id)}
        >
          ${J}
          <span>Complete</span>
        </button>
      </div>
    `;
  }
  _renderRollup() {
    const t = this._otherChildren();
    if (t.length === 0)
      return m;
    const e = t.slice(0, 2).map((n) => n.present ? n.due > 0 && n.completed >= n.due ? `${n.name} has finished their log.` : n.due > n.completed ? `${n.name} has ${n.due - n.completed} quests left.` : `${n.name} has no quests today.` : n.returnsWeekday ? `${n.name} is on travels until ${n.returnsWeekday}.` : `${n.name} is on travels.`);
    return g`
      <div class="rollup">
        <span class="rollup-label">Party roll-up</span>
        <p class="rollup-body">${e.join(" ")}</p>
      </div>
    `;
  }
  _renderConfirm() {
    if (this._confirm === null)
      return m;
    const t = this._instances().find(
      (n) => n.id === this._confirm
    );
    if (!t)
      return m;
    const e = Et.find((n) => n.key === t.window);
    return g`
      <div class="scrim" @click=${() => this._closeConfirm()}>
        <div
          class="dialog"
          role="dialog"
          aria-modal="true"
          @click=${(n) => n.stopPropagation()}
        >
          <div class="dialog-header">
            <span class="dialog-tile" aria-hidden="true">${G}</span>
            <div class="dialog-titles">
              <span class="dialog-kicker">
                ${e?.name ?? "Quest"}
              </span>
              <span class="dialog-quest-title">${t.title}</span>
            </div>
          </div>
          <p class="dialog-body">
            Mark this quest complete? Once the seal is set, only a parent can
            undo it.
          </p>
          <div class="dialog-buttons">
            <button
              class="confirm-button not-yet"
              type="button"
              @click=${() => this._closeConfirm()}
            >
              ${He}
              <span>Not yet</span>
            </button>
            <button
              class="confirm-button do-complete"
              type="button"
              @click=${() => this._confirmComplete()}
            >
              ${J}
              <span>Complete</span>
            </button>
          </div>
        </div>
      </div>
    `;
  }
  _openConfirm(t) {
    this._confirm = t, this._armConfirmTimer();
  }
  _closeConfirm() {
    this._clearConfirmTimer(), this._confirm = null;
  }
  _confirmComplete() {
    this._closeConfirm();
  }
  _armConfirmTimer() {
    this._clearConfirmTimer(), this._confirmTimer = window.setTimeout(() => {
      this._confirmTimer = void 0, this._closeConfirm();
    }, this._confirmSeconds() * 1e3);
  }
  _clearConfirmTimer() {
    this._confirmTimer !== void 0 && (window.clearTimeout(this._confirmTimer), this._confirmTimer = void 0);
  }
  _armIdle() {
    this._clearIdle(), this._idleTimer = window.setTimeout(() => {
      this._idleTimer = void 0, this._returnToBoard();
    }, this._idleSeconds() * 1e3);
  }
  _clearIdle() {
    this._idleTimer !== void 0 && (window.clearTimeout(this._idleTimer), this._idleTimer = void 0);
  }
  _returnToBoard() {
    const t = this._boardPath();
    t && (window.history.pushState(null, "", t), window.dispatchEvent(new Event("location-changed")));
  }
  _stopClock() {
    this._clockTimer !== void 0 && (window.clearInterval(this._clockTimer), this._clockTimer = void 0);
  }
  _onActivity = () => {
    this._armIdle(), this._confirm !== null && this._armConfirmTimer();
  };
}
customElements.define("nestquest-quest-log-card", Be);
st({
  type: "nestquest-quest-log-card",
  name: "NestQuest Quest Log",
  description: "One child's daily quests, grouped by window."
});
const Fe = ":host{--nq-brand-blue: #3B3AB8;--nq-brand-purple: #A035CC;--nq-brand-gradient: linear-gradient(135deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-brand-gradient-h: linear-gradient(90deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-a-page: #F4F4F6;--nq-a-surface: #FFFFFF;--nq-a-surface-subtle: #FAFAFA;--nq-a-selected: #EBEBF8;--nq-a-border: #E4E4EA;--nq-a-divider: #EDEDF1;--nq-a-ink: #18181D;--nq-a-ink-secondary: #52525E;--nq-a-ink-tertiary: #70707E;--nq-a-success: #15803D;--nq-a-danger: #DC2626;--nq-a-danger-strong: #B91C1C;--nq-a-danger-bg: #FEE2E2;--nq-a-warning-ink: #92400E;--nq-a-warning-ink-2: #78350F;--nq-a-warning-bg: #FEF3C7;--nq-a-warning-border: rgba(217,119,6,.35);--nq-a-info-bg: #DBEAFE;--nq-a-info-ink: #1E3A8A;--nq-a-info-icon: #1D4ED8;--nq-a-reversal: #7D28A0;--nq-a-font: Nunito, system-ui, sans-serif;--nq-a-size-screen: 24px;--nq-a-size-hero: 32px;--nq-a-size-card-title: 19px;--nq-a-size-stat: 22px;--nq-a-size-row: 13.5px;--nq-a-size-meta: 11px;--nq-a-size-label: 10px;--nq-a-track-label: .1em;--nq-a-density-page-pad: 14px 16px 92px;--nq-a-density-gap: 10px;--nq-a-density-card-pad: 13px;--nq-a-density-row-pad: 11px 13px;--nq-a-density-radius: 8px;--nq-a-density-shadow: none;--nq-a-tabbar-height: 70px;--nq-a-tap-min: 44px;--nq-a-radius-pill: 9999px;--nq-a-radius-sheet: 20px 20px 0 0;--nq-a-sheet-shadow: 0 -8px 28px rgba(9,9,11,.18);--nq-a-progress-height: 6px;--nq-ease-out: cubic-bezier(0, 0, .2, 1);--nq-dur-micro: .12s;--nq-dur-base: .2s;--nq-dur-modal: .35s}";
class Qe extends C {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 }
  };
  static styles = [b(Fe)];
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
customElements.define("nestquest-admin-card", Qe);
st({
  type: "nestquest-admin-card",
  name: "NestQuest Admin",
  description: "Parent phone view for today, tasks, schedule, and history."
});
const We = "/nestquest-static/nestquest-fonts.css";
if (!document.querySelector('link[data-nq-fonts=""]')) {
  const i = document.createElement("link");
  i.rel = "stylesheet", i.href = We, i.dataset.nqFonts = "", document.head.appendChild(i);
}

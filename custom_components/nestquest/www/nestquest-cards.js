const B = globalThis, nt = B.ShadowRoot && (B.ShadyCSS === void 0 || B.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, st = /* @__PURE__ */ Symbol(), lt = /* @__PURE__ */ new WeakMap();
let zt = class {
  constructor(t, e, n) {
    if (this._$cssResult$ = !0, n !== st) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = t, this.t = e;
  }
  get styleSheet() {
    let t = this.o;
    const e = this.t;
    if (nt && t === void 0) {
      const n = e !== void 0 && e.length === 1;
      n && (t = lt.get(e)), t === void 0 && ((this.o = t = new CSSStyleSheet()).replaceSync(this.cssText), n && lt.set(e, t));
    }
    return t;
  }
  toString() {
    return this.cssText;
  }
};
const v = (s) => new zt(typeof s == "string" ? s : s + "", void 0, st), Pt = (s, ...t) => {
  const e = s.length === 1 ? s[0] : t.reduce((n, i, r) => n + ((o) => {
    if (o._$cssResult$ === !0) return o.cssText;
    if (typeof o == "number") return o;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + o + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(i) + s[r + 1], s[0]);
  return new zt(e, s, st);
}, Ft = (s, t) => {
  if (nt) s.adoptedStyleSheets = t.map((e) => e instanceof CSSStyleSheet ? e : e.styleSheet);
  else for (const e of t) {
    const n = document.createElement("style"), i = B.litNonce;
    i !== void 0 && n.setAttribute("nonce", i), n.textContent = e.cssText, s.appendChild(n);
  }
}, ct = nt ? (s) => s : (s) => s instanceof CSSStyleSheet ? ((t) => {
  let e = "";
  for (const n of t.cssRules) e += n.cssText;
  return v(e);
})(s) : s;
const { is: Qt, defineProperty: Wt, getOwnPropertyDescriptor: Zt, getOwnPropertyNames: Gt, getOwnPropertySymbols: Vt, getPrototypeOf: Kt } = Object, W = globalThis, dt = W.trustedTypes, Jt = dt ? dt.emptyScript : "", Xt = W.reactiveElementPolyfillSupport, I = (s, t) => s, et = { toAttribute(s, t) {
  switch (t) {
    case Boolean:
      s = s ? Jt : null;
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
} }, It = (s, t) => !Qt(s, t), pt = { attribute: !0, type: String, converter: et, reflect: !1, useDefault: !1, hasChanged: It };
Symbol.metadata ??= /* @__PURE__ */ Symbol("metadata"), W.litPropertyMetadata ??= /* @__PURE__ */ new WeakMap();
let E = class extends HTMLElement {
  static addInitializer(t) {
    this._$Ei(), (this.l ??= []).push(t);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(t, e = pt) {
    if (e.state && (e.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(t) && ((e = Object.create(e)).wrapped = !0), this.elementProperties.set(t, e), !e.noAccessor) {
      const n = /* @__PURE__ */ Symbol(), i = this.getPropertyDescriptor(t, n, e);
      i !== void 0 && Wt(this.prototype, t, i);
    }
  }
  static getPropertyDescriptor(t, e, n) {
    const { get: i, set: r } = Zt(this.prototype, t) ?? { get() {
      return this[e];
    }, set(o) {
      this[e] = o;
    } };
    return { get: i, set(o) {
      const l = i?.call(this);
      r?.call(this, o), this.requestUpdate(t, l, n);
    }, configurable: !0, enumerable: !0 };
  }
  static getPropertyOptions(t) {
    return this.elementProperties.get(t) ?? pt;
  }
  static _$Ei() {
    if (this.hasOwnProperty(I("elementProperties"))) return;
    const t = Kt(this);
    t.finalize(), t.l !== void 0 && (this.l = [...t.l]), this.elementProperties = new Map(t.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(I("finalized"))) return;
    if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(I("properties"))) {
      const e = this.properties, n = [...Gt(e), ...Vt(e)];
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
      for (const i of n) e.unshift(ct(i));
    } else t !== void 0 && e.push(ct(t));
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
    return Ft(t, this.constructor.elementStyles), t;
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
      const r = (n.converter?.toAttribute !== void 0 ? n.converter : et).toAttribute(e, n.type);
      this._$Em = t, r == null ? this.removeAttribute(i) : this.setAttribute(i, r), this._$Em = null;
    }
  }
  _$AK(t, e) {
    const n = this.constructor, i = n._$Eh.get(t);
    if (i !== void 0 && this._$Em !== i) {
      const r = n.getPropertyOptions(i), o = typeof r.converter == "function" ? { fromAttribute: r.converter } : r.converter?.fromAttribute !== void 0 ? r.converter : et;
      this._$Em = i;
      const l = o.fromAttribute(e, r.type);
      this[i] = l ?? this._$Ej?.get(i) ?? l, this._$Em = null;
    }
  }
  requestUpdate(t, e, n, i = !1, r) {
    if (t !== void 0) {
      const o = this.constructor;
      if (i === !1 && (r = this[t]), n ??= o.getPropertyOptions(t), !((n.hasChanged ?? It)(r, e) || n.useDefault && n.reflect && r === this._$Ej?.get(t) && !this.hasAttribute(o._$Eu(t, n)))) return;
      this.C(t, e, n);
    }
    this.isUpdatePending === !1 && (this._$ES = this._$EP());
  }
  C(t, e, { useDefault: n, reflect: i, wrapped: r }, o) {
    n && !(this._$Ej ??= /* @__PURE__ */ new Map()).has(t) && (this._$Ej.set(t, o ?? e ?? this[t]), r !== !0 || o !== void 0) || (this._$AL.has(t) || (this.hasUpdated || n || (e = void 0), this._$AL.set(t, e)), i === !0 && this._$Em !== t && (this._$Eq ??= /* @__PURE__ */ new Set()).add(t));
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
        const { wrapped: o } = r, l = this[i];
        o !== !0 || this._$AL.has(i) || l === void 0 || this.C(i, void 0, r, l);
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
E.elementStyles = [], E.shadowRootOptions = { mode: "open" }, E[I("elementProperties")] = /* @__PURE__ */ new Map(), E[I("finalized")] = /* @__PURE__ */ new Map(), Xt?.({ ReactiveElement: E }), (W.reactiveElementVersions ??= []).push("2.1.2");
const it = globalThis, ht = (s) => s, F = it.trustedTypes, ut = F ? F.createPolicy("lit-html", { createHTML: (s) => s }) : void 0, Lt = "$lit$", $ = `lit$${Math.random().toFixed(9).slice(2)}$`, Ut = "?" + $, Yt = `<${Ut}>`, S = document, L = () => S.createComment(""), U = (s) => s === null || typeof s != "object" && typeof s != "function", rt = Array.isArray, te = (s) => rt(s) || typeof s?.[Symbol.iterator] == "function", V = `[ 	
\f\r]`, z = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, ft = /-->/g, mt = />/g, q = RegExp(`>|${V}(?:([^\\s"'>=/]+)(${V}*=${V}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g"), gt = /'/g, _t = /"/g, Rt = /^(?:script|style|textarea|title)$/i, ee = (s) => (t, ...e) => ({ _$litType$: s, strings: t, values: e }), d = ee(1), T = /* @__PURE__ */ Symbol.for("lit-noChange"), g = /* @__PURE__ */ Symbol.for("lit-nothing"), yt = /* @__PURE__ */ new WeakMap(), C = S.createTreeWalker(S, 129);
function jt(s, t) {
  if (!rt(s) || !s.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return ut !== void 0 ? ut.createHTML(t) : t;
}
const ne = (s, t) => {
  const e = s.length - 1, n = [];
  let i, r = t === 2 ? "<svg>" : t === 3 ? "<math>" : "", o = z;
  for (let l = 0; l < e; l++) {
    const a = s[l];
    let p, u, c = -1, f = 0;
    for (; f < a.length && (o.lastIndex = f, u = o.exec(a), u !== null); ) f = o.lastIndex, o === z ? u[1] === "!--" ? o = ft : u[1] !== void 0 ? o = mt : u[2] !== void 0 ? (Rt.test(u[2]) && (i = RegExp("</" + u[2], "g")), o = q) : u[3] !== void 0 && (o = q) : o === q ? u[0] === ">" ? (o = i ?? z, c = -1) : u[1] === void 0 ? c = -2 : (c = o.lastIndex - u[2].length, p = u[1], o = u[3] === void 0 ? q : u[3] === '"' ? _t : gt) : o === _t || o === gt ? o = q : o === ft || o === mt ? o = z : (o = q, i = void 0);
    const h = o === q && s[l + 1].startsWith("/>") ? " " : "";
    r += o === z ? a + Yt : c >= 0 ? (n.push(p), a.slice(0, c) + Lt + a.slice(c) + $ + h) : a + $ + (c === -2 ? l : h);
  }
  return [jt(s, r + (s[e] || "<?>") + (t === 2 ? "</svg>" : t === 3 ? "</math>" : "")), n];
};
class R {
  constructor({ strings: t, _$litType$: e }, n) {
    let i;
    this.parts = [];
    let r = 0, o = 0;
    const l = t.length - 1, a = this.parts, [p, u] = ne(t, e);
    if (this.el = R.createElement(p, n), C.currentNode = this.el.content, e === 2 || e === 3) {
      const c = this.el.content.firstChild;
      c.replaceWith(...c.childNodes);
    }
    for (; (i = C.nextNode()) !== null && a.length < l; ) {
      if (i.nodeType === 1) {
        if (i.hasAttributes()) for (const c of i.getAttributeNames()) if (c.endsWith(Lt)) {
          const f = u[o++], h = i.getAttribute(c).split($), m = /([.?@])?(.*)/.exec(f);
          a.push({ type: 1, index: r, name: m[2], strings: h, ctor: m[1] === "." ? ie : m[1] === "?" ? re : m[1] === "@" ? oe : Z }), i.removeAttribute(c);
        } else c.startsWith($) && (a.push({ type: 6, index: r }), i.removeAttribute(c));
        if (Rt.test(i.tagName)) {
          const c = i.textContent.split($), f = c.length - 1;
          if (f > 0) {
            i.textContent = F ? F.emptyScript : "";
            for (let h = 0; h < f; h++) i.append(c[h], L()), C.nextNode(), a.push({ type: 2, index: ++r });
            i.append(c[f], L());
          }
        }
      } else if (i.nodeType === 8) if (i.data === Ut) a.push({ type: 2, index: r });
      else {
        let c = -1;
        for (; (c = i.data.indexOf($, c + 1)) !== -1; ) a.push({ type: 7, index: r }), c += $.length - 1;
      }
      r++;
    }
  }
  static createElement(t, e) {
    const n = S.createElement("template");
    return n.innerHTML = t, n;
  }
}
function N(s, t, e = s, n) {
  if (t === T) return t;
  let i = n !== void 0 ? e._$Co?.[n] : e._$Cl;
  const r = U(t) ? void 0 : t._$litDirective$;
  return i?.constructor !== r && (i?._$AO?.(!1), r === void 0 ? i = void 0 : (i = new r(s), i._$AT(s, e, n)), n !== void 0 ? (e._$Co ??= [])[n] = i : e._$Cl = i), i !== void 0 && (t = N(s, i._$AS(s, t.values), i, n)), t;
}
class se {
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
    const { el: { content: e }, parts: n } = this._$AD, i = (t?.creationScope ?? S).importNode(e, !0);
    C.currentNode = i;
    let r = C.nextNode(), o = 0, l = 0, a = n[0];
    for (; a !== void 0; ) {
      if (o === a.index) {
        let p;
        a.type === 2 ? p = new O(r, r.nextSibling, this, t) : a.type === 1 ? p = new a.ctor(r, a.name, a.strings, this, t) : a.type === 6 && (p = new ae(r, this, t)), this._$AV.push(p), a = n[++l];
      }
      o !== a?.index && (r = C.nextNode(), o++);
    }
    return C.currentNode = S, i;
  }
  p(t) {
    let e = 0;
    for (const n of this._$AV) n !== void 0 && (n.strings !== void 0 ? (n._$AI(t, n, e), e += n.strings.length - 2) : n._$AI(t[e])), e++;
  }
}
class O {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(t, e, n, i) {
    this.type = 2, this._$AH = g, this._$AN = void 0, this._$AA = t, this._$AB = e, this._$AM = n, this.options = i, this._$Cv = i?.isConnected ?? !0;
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
    t = N(this, t, e), U(t) ? t === g || t == null || t === "" ? (this._$AH !== g && this._$AR(), this._$AH = g) : t !== this._$AH && t !== T && this._(t) : t._$litType$ !== void 0 ? this.$(t) : t.nodeType !== void 0 ? this.T(t) : te(t) ? this.k(t) : this._(t);
  }
  O(t) {
    return this._$AA.parentNode.insertBefore(t, this._$AB);
  }
  T(t) {
    this._$AH !== t && (this._$AR(), this._$AH = this.O(t));
  }
  _(t) {
    this._$AH !== g && U(this._$AH) ? this._$AA.nextSibling.data = t : this.T(S.createTextNode(t)), this._$AH = t;
  }
  $(t) {
    const { values: e, _$litType$: n } = t, i = typeof n == "number" ? this._$AC(t) : (n.el === void 0 && (n.el = R.createElement(jt(n.h, n.h[0]), this.options)), n);
    if (this._$AH?._$AD === i) this._$AH.p(e);
    else {
      const r = new se(i, this), o = r.u(this.options);
      r.p(e), this.T(o), this._$AH = r;
    }
  }
  _$AC(t) {
    let e = yt.get(t.strings);
    return e === void 0 && yt.set(t.strings, e = new R(t)), e;
  }
  k(t) {
    rt(this._$AH) || (this._$AH = [], this._$AR());
    const e = this._$AH;
    let n, i = 0;
    for (const r of t) i === e.length ? e.push(n = new O(this.O(L()), this.O(L()), this, this.options)) : n = e[i], n._$AI(r), i++;
    i < e.length && (this._$AR(n && n._$AB.nextSibling, i), e.length = i);
  }
  _$AR(t = this._$AA.nextSibling, e) {
    for (this._$AP?.(!1, !0, e); t !== this._$AB; ) {
      const n = ht(t).nextSibling;
      ht(t).remove(), t = n;
    }
  }
  setConnected(t) {
    this._$AM === void 0 && (this._$Cv = t, this._$AP?.(t));
  }
}
class Z {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(t, e, n, i, r) {
    this.type = 1, this._$AH = g, this._$AN = void 0, this.element = t, this.name = e, this._$AM = i, this.options = r, n.length > 2 || n[0] !== "" || n[1] !== "" ? (this._$AH = Array(n.length - 1).fill(new String()), this.strings = n) : this._$AH = g;
  }
  _$AI(t, e = this, n, i) {
    const r = this.strings;
    let o = !1;
    if (r === void 0) t = N(this, t, e, 0), o = !U(t) || t !== this._$AH && t !== T, o && (this._$AH = t);
    else {
      const l = t;
      let a, p;
      for (t = r[0], a = 0; a < r.length - 1; a++) p = N(this, l[n + a], e, a), p === T && (p = this._$AH[a]), o ||= !U(p) || p !== this._$AH[a], p === g ? t = g : t !== g && (t += (p ?? "") + r[a + 1]), this._$AH[a] = p;
    }
    o && !i && this.j(t);
  }
  j(t) {
    t === g ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, t ?? "");
  }
}
class ie extends Z {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(t) {
    this.element[this.name] = t === g ? void 0 : t;
  }
}
class re extends Z {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(t) {
    this.element.toggleAttribute(this.name, !!t && t !== g);
  }
}
class oe extends Z {
  constructor(t, e, n, i, r) {
    super(t, e, n, i, r), this.type = 5;
  }
  _$AI(t, e = this) {
    if ((t = N(this, t, e, 0) ?? g) === T) return;
    const n = this._$AH, i = t === g && n !== g || t.capture !== n.capture || t.once !== n.once || t.passive !== n.passive, r = t !== g && (n === g || i);
    i && this.element.removeEventListener(this.name, this, n), r && this.element.addEventListener(this.name, this, t), this._$AH = t;
  }
  handleEvent(t) {
    typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, t) : this._$AH.handleEvent(t);
  }
}
class ae {
  constructor(t, e, n) {
    this.element = t, this.type = 6, this._$AN = void 0, this._$AM = e, this.options = n;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t) {
    N(this, t);
  }
}
const le = { I: O }, ce = it.litHtmlPolyfillSupport;
ce?.(R, O), (it.litHtmlVersions ??= []).push("3.3.3");
const de = (s, t, e) => {
  const n = e?.renderBefore ?? t;
  let i = n._$litPart$;
  if (i === void 0) {
    const r = e?.renderBefore ?? null;
    n._$litPart$ = i = new O(t.insertBefore(L(), r), r, void 0, e ?? {});
  }
  return i._$AI(s), i;
};
const ot = globalThis;
let A = class extends E {
  constructor() {
    super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
  }
  createRenderRoot() {
    const t = super.createRenderRoot();
    return this.renderOptions.renderBefore ??= t.firstChild, t;
  }
  update(t) {
    const e = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t), this._$Do = de(e, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(!0);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(!1);
  }
  render() {
    return T;
  }
};
A._$litElement$ = !0, A.finalized = !0, ot.litElementHydrateSupport?.({ LitElement: A });
const pe = ot.litElementPolyfillSupport;
pe?.({ LitElement: A });
(ot.litElementVersions ??= []).push("4.2.2");
const Dt = ':host{--nq-p-parchment-top: #f0e4c7;--nq-p-parchment-bottom: #ddcca3;--nq-p-parchment: radial-gradient(ellipse at 25% 10%, rgba(255,255,255,.5), transparent 55%), radial-gradient(ellipse at 85% 90%, rgba(120,86,44,.28), transparent 60%), repeating-linear-gradient(93deg, rgba(150,115,70,.05) 0 2px, transparent 2px 6px), repeating-linear-gradient(2deg, rgba(150,115,70,.04) 0 3px, transparent 3px 7px), linear-gradient(var(--nq-p-parchment-top), var(--nq-p-parchment-bottom));--nq-p-vignette: inset 0 0 200px rgba(80,52,20,.35);--nq-p-card-open: linear-gradient(#fdf7e6, #f2e7c9);--nq-p-card-done: linear-gradient(#f0e8d3, #e6dcc2);--nq-p-card-panel: linear-gradient(#fcf6e6, #f1e6ca);--nq-p-card-border: rgba(120,88,48,.38);--nq-p-panel-border: rgba(92,62,26,.4);--nq-p-card-shadow: 0 3px 0 rgba(120,88,48,.2), inset 0 1px 0 rgba(255,255,255,.7);--nq-p-panel-shadow: 0 6px 0 rgba(92,62,26,.18), inset 0 2px 0 rgba(255,255,255,.7);--nq-p-frame-outer: 2px solid rgba(92,62,26,.45);--nq-p-frame-inner: 1px solid rgba(92,62,26,.28);--nq-p-rule: 2px solid rgba(92,62,26,.35);--nq-p-ink: #2b1f14;--nq-p-ink-secondary: #5c452a;--nq-p-ink-muted: #6f6455;--nq-p-ink-away: #4d4433;--nq-p-ink-late: #8f1526;--nq-brand-blue: #3B3AB8;--nq-brand-purple: #A035CC;--nq-brand-gradient: linear-gradient(135deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-p-icon-tile: var(--nq-brand-gradient);--nq-p-icon-tile-done: rgba(92,62,26,.16);--nq-p-crest: var(--nq-brand-gradient);--nq-p-crest-away: linear-gradient(135deg, #6b6b7a, #7a7286);--nq-p-seal: radial-gradient(circle at 35% 30%, #a8283a, #6d1322);--nq-p-seal-shadow: 0 4px 10px rgba(60,10,20,.4), inset 0 0 0 4px rgba(255,255,255,.14);--nq-p-seal-size: 78px;--nq-p-dock-bg: rgba(43,31,20,.9);--nq-p-dock-ink: #f7efdb;--nq-p-dock-ink-secondary: #d8c9a6;--nq-p-dock-divider: rgba(233,220,189,.3);--nq-p-dock-height: 84px;--nq-p-font-display: "Cinzel Decorative", Cinzel, serif;--nq-p-font-heading: Cinzel, serif;--nq-p-font-body: Nunito, system-ui, sans-serif;--nq-p-size-hero: 86px;--nq-p-size-wordmark: 66px;--nq-p-size-title: 56px;--nq-p-size-name: 48px;--nq-p-size-section: 32px;--nq-p-size-quest: 30px;--nq-p-size-body: 22px;--nq-p-size-label: 21px;--nq-p-track-label: .14em;--nq-p-track-kicker: .3em;--nq-p-quest-min-height: 116px;--nq-p-quest-gap: 24px;--nq-p-quest-pad: 22px;--nq-p-tile-size: 64px;--nq-p-button-height: 72px;--nq-p-button-min-width: 150px;--nq-p-confirm-button: 108px;--nq-p-radius-card: 12px;--nq-p-radius-panel: 20px;--nq-p-radius-pill: 9999px;--nq-p-page-inset: 62px;--nq-p-frame-inset: 26px;--nq-ease-out: cubic-bezier(0, 0, .2, 1);--nq-dur-micro: .12s;--nq-dur-base: .2s;--nq-dur-modal: .35s}';
function at(s) {
  window.customCards = window.customCards ?? [], window.customCards.push(s);
}
const he = [
  "nestquest_quest_completed",
  "nestquest_quest_uncompleted",
  "nestquest_quest_missed",
  "nestquest_child_day_complete"
], bt = /* @__PURE__ */ new Map();
function Q(s, t) {
  const e = `${s ?? "local"}|${JSON.stringify(t)}`, n = bt.get(e);
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
  return bt.set(e, i), i;
}
function ue(s) {
  const t = s?.config;
  if (!t || typeof t != "object")
    return;
  const e = t.time_zone;
  return typeof e == "string" && e.trim() ? e.trim() : void 0;
}
function K(s, t) {
  return `${Q(t, { weekday: "long" }).format(s)}, ${Q(t, { month: "short", day: "numeric" }).format(s)}`;
}
function fe(s, t) {
  return Q(t, {
    hour: "numeric",
    minute: "2-digit",
    hour12: !0
  }).format(s);
}
const me = {
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
}, ge = {
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
function vt(s) {
  return typeof s == "string" ? s.trim() : "";
}
function J(s, t) {
  if (s == null || s === "")
    return t;
  const e = typeof s == "number" ? s : Number(s);
  return Number.isFinite(e) ? e : t;
}
function _e(s) {
  if (s === null || typeof s != "object" || Array.isArray(s))
    return "";
  const t = s.slug;
  return typeof t == "string" ? t.trim() : "";
}
function xt(s) {
  return Number.isFinite(s) ? Math.min(100, Math.max(0, s)) : 0;
}
function wt(s) {
  return Math.max(0, Math.round(s));
}
function ye(s) {
  return s.split(/[-_]+/).filter(Boolean).map((t) => t.charAt(0).toUpperCase() + t.slice(1)).join(" ");
}
function be(s, t) {
  const e = Q(t, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23"
  }).formatToParts(new Date(s)), n = (r) => {
    const o = e.find((l) => l.type === r);
    return o ? Number(o.value) : Number.NaN;
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
function ve(s, t) {
  if (typeof s != "string")
    return null;
  const e = s.split("-");
  if (e.length !== 3)
    return null;
  const [n, i, r] = e.map((a) => Number(a));
  if (!n || !i || !r)
    return null;
  if (!t) {
    const a = new Date(n, i - 1, r);
    return Number.isNaN(a.getTime()) ? null : a;
  }
  const o = Date.UTC(n, i - 1, r), l = new Date(o - be(o, t));
  return Number.isNaN(l.getTime()) ? null : l;
}
function xe(s) {
  const t = me[s];
  return t || s.charAt(0).toUpperCase() + s.slice(1);
}
function we(s, t) {
  return ge[s] ?? t;
}
const $t = "polygon(0 0, 100% 0, 100% 62%, 50% 100%, 0 62%)", $e = "polygon(50% 0, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)", qe = Pt`
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
    clip-path: ${v($e)};
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
    clip-path: ${v($t)};
    background: rgba(255, 255, 255, 0.22);
  }

  .crest-face {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-bottom: 70px;
    clip-path: ${v($t)};
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
    top: 896px;
    left: 0;
    right: 0;
    margin: 0;
    font-family: var(--nq-p-font-body);
    font-size: 27px;
    font-weight: 600;
    line-height: 1.4;
    text-align: center;
    color: var(--nq-p-ink-secondary);
  }

  .plate.unknown {
    border: 2px dashed var(--nq-p-panel-border);
    background: linear-gradient(#f2ecdd, #e6dcc6);
    box-shadow: none;
  }

  .notice-wrap {
    position: absolute;
    top: 262px;
    left: 110px;
    right: 110px;
    bottom: 190px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .notice {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 20px;
    width: 100%;
    max-width: 980px;
    padding: 56px 64px;
    border: 2px solid var(--nq-p-panel-border);
    border-radius: var(--nq-p-radius-panel);
    background: var(--nq-p-card-panel);
    box-shadow: var(--nq-p-panel-shadow);
    text-align: center;
  }

  .notice svg {
    width: 46px;
    height: 46px;
    color: var(--nq-p-ink-secondary);
  }

  .notice-headline {
    font-family: var(--nq-p-font-heading);
    font-size: 40px;
    font-weight: 700;
    line-height: 1.15;
    color: var(--nq-p-ink);
  }

  .notice-body {
    margin: 0;
    font-family: var(--nq-p-font-body);
    font-size: 24px;
    font-weight: 600;
    line-height: 1.4;
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
`, ke = d`<svg
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
</svg>`, Ce = d`<svg
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
</svg>`, Ae = d`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <circle cx="12" cy="12" r="10"></circle>
  <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon>
</svg>`, Se = d`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path>
  <path d="M12 9v4"></path>
  <path d="M12 17h.01"></path>
</svg>`, Te = d`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"></path>
  <path d="m2 2 20 20"></path>
</svg>`, qt = {
  icon: Se,
  headline: "NestQuest is not set up yet",
  body: "A parent needs to finish setting up NestQuest before the party can gather."
}, Ee = {
  icon: Te,
  headline: "The records cannot be reached",
  body: "The party's records are quiet right now. NestQuest will return shortly."
}, Ne = d`<svg
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
class Me extends A {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 },
    _now: { state: !0 }
  };
  static styles = [v(Dt), qe];
  hass;
  _config;
  _now = /* @__PURE__ */ new Date();
  _clockTimer;
  _unsubs = [];
  _subscribed = !1;
  _subGeneration = 0;
  _retryTimer;
  setConfig(t) {
    if (!t || typeof t != "object")
      throw new Error("Invalid configuration");
    this._config = t;
  }
  _hassConnection() {
    const t = this.hass?.connection;
    return !t || typeof t != "object" || typeof t.subscribeEvents != "function" ? null : t;
  }
  _subscribeLive() {
    if (!this.isConnected || this._subscribed)
      return;
    const t = this._hassConnection();
    if (!t)
      return;
    this._subscribed = !0;
    const e = ++this._subGeneration, n = (i) => {
      i.then((r) => {
        this._subscribed && e === this._subGeneration ? this._unsubs.push(r) : r();
      }).catch(() => {
        e === this._subGeneration && (this._unsubscribeLive(), this._armSubscribeRetry());
      });
    };
    for (const i of he)
      n(
        t.subscribeEvents(() => this.requestUpdate(), i)
      );
  }
  _armSubscribeRetry() {
    this._retryTimer === void 0 && (this._retryTimer = window.setTimeout(() => {
      this._retryTimer = void 0, this._subscribeLive();
    }, 1e3));
  }
  _clearSubscribeRetry() {
    this._retryTimer !== void 0 && (window.clearTimeout(this._retryTimer), this._retryTimer = void 0);
  }
  _unsubscribeLive() {
    this._clearSubscribeRetry(), this._subGeneration++;
    for (const t of this._unsubs)
      t();
    this._unsubs = [], this._subscribed = !1;
  }
  getCardSize() {
    return 22;
  }
  connectedCallback() {
    super.connectedCallback(), this._subscribeLive(), this._now = /* @__PURE__ */ new Date(), this._clockTimer = window.setInterval(() => {
      this._now = /* @__PURE__ */ new Date();
    }, 1e3);
  }
  updated() {
    this._subscribeLive();
  }
  disconnectedCallback() {
    this._unsubscribeLive(), this._clockTimer !== void 0 && (window.clearInterval(this._clockTimer), this._clockTimer = void 0), super.disconnectedCallback();
  }
  render() {
    const t = this._boardNotice();
    return d`
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
        <p class="kicker">The Party · ${K(this._now, this._timeZone())}</p>
        ${t ? this._renderNotice(t) : d`
              <div class="plates">
                ${this._plates().map((e) => this._renderPlate(e))}
              </div>
              <p class="hint">Tap your crest to open your Quest Log</p>
            `}
        <div class="spacer"></div>
        ${this._renderDock()}
      </div>
    `;
  }
  _timeZone() {
    return ue(this.hass);
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
    ).map((e) => e.trim()) : this._discoveredChildSlugs();
  }
  /** Zero-config discovery (Feature 20): the ordered child roster the
   *  integration publishes on the household rollup
   *  (custom_components/nestquest/sensor.py — ``child_roster``, the
   *  snapshot's sort_order, then id), each entry carrying the slug the
   *  per-child entity ids are built from.  Consulted only when the
   *  config has no child_order — explicit configuration wins. */
  _discoveredChildSlugs() {
    const e = this._state(
      "sensor.nestquest_household_quests_due_today"
    )?.attributes?.child_roster;
    return Array.isArray(e) ? e.map((n) => _e(n)).filter((n) => n.length > 0) : [];
  }
  _plates() {
    return this._childSlugs().map((t) => this._plate(t));
  }
  _plate(t) {
    const e = this._dueSensorResolution(t), n = this._state(`sensor.nestquest_${t}_quests_due_today`), i = this._state(
      `sensor.nestquest_${t}_quests_completed_today`
    ), r = this._state(
      `sensor.nestquest_${t}_completion_pct_today`
    ), o = this._state(
      `binary_sensor.nestquest_${t}_present_today`
    ), l = n?.attributes ?? {}, a = wt(J(n?.state, 0)), p = wt(J(i?.state, 0)), u = r ? J(r.state, Number.NaN) : Number.NaN, c = Number.isFinite(u) ? xt(u) : a > 0 ? xt(p / a * 100) : 0;
    let f = !0;
    const h = l.present;
    typeof h == "boolean" ? f = h : o && (f = String(o.state ?? "").trim().toLowerCase() === "on");
    let m = "";
    const _ = l.child_name;
    if (typeof _ == "string" && _.trim())
      m = _.trim();
    else {
      const G = o?.attributes?.child_name;
      typeof G == "string" && G.trim() && (m = G.trim());
    }
    m || (m = ye(t));
    const x = ve(
      o?.attributes?.next_present,
      this._timeZone()
    ), j = x ? `Returns ${K(x, this._timeZone())}` : null;
    return {
      slug: t,
      name: m,
      initial: (m.charAt(0) || "?").toUpperCase(),
      present: e === null ? f : !1,
      completed: p,
      due: a,
      pct: c,
      returns: j,
      unresolved: e
    };
  }
  /** "missing" when the due sensor does not exist (integration not
   *  configured), "stale" when it answers unavailable/unknown (backend
   *  unreachable or the child is absent from the snapshot), null when
   *  it resolves. */
  _dueSensorResolution(t) {
    const e = this._state(`sensor.nestquest_${t}_quests_due_today`);
    if (!e)
      return "missing";
    const n = String(e.state ?? "").trim().toLowerCase();
    return !n || n === "unavailable" || n === "unknown" ? "stale" : null;
  }
  _boardNotice() {
    const t = this._plates();
    return t.length === 0 ? qt : t.every((e) => e.unresolved !== null) ? t.some((e) => e.unresolved === "stale") ? Ee : qt : null;
  }
  _renderNotice(t) {
    return d`
      <div class="notice-wrap">
        <div class="notice" role="status">
          ${t.icon}
          <span class="notice-headline">${t.headline}</span>
          <p class="notice-body">${t.body}</p>
        </div>
      </div>
    `;
  }
  _renderPlate(t) {
    return t.unresolved ? d`
        <div class="plate unknown">
          <span class="crest away">
            <span class="crest-face">
              <span class="initial">${t.initial}</span>
            </span>
          </span>
          <span class="name">${t.name}</span>
          <span class="pill away">
            ${Ae}
            <span>Unknown</span>
          </span>
          <span class="progress-line">&mdash;</span>
          <span class="bar"></span>
        </div>
      ` : t.present ? d`
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
            ${ke}
            <span>Home today</span>
          </span>
          <span class="progress-line">
            ${t.completed} of ${t.due} quests claimed
          </span>
          <span class="bar">
            <span class="fill" style="width: ${t.pct}%"></span>
          </span>
        </button>
      ` : d`
      <div class="plate away">
        <span class="crest away">
          <span class="crest-face">
            <span class="initial">${t.initial}</span>
          </span>
        </span>
        <span class="name">${t.name}</span>
        <span class="pill away">
          ${Ce}
          <span>On travels</span>
        </span>
        <span class="progress-line">${t.returns ?? "Returns —"}</span>
        <span class="bar"></span>
      </div>
    `;
  }
  _openQuestLog(t) {
    const e = vt(this._config?.quest_log_path);
    e && (window.history.pushState(null, "", `${e.replace(/\/+$/, "")}/${t}`), window.dispatchEvent(new Event("location-changed")));
  }
  _dockWeather() {
    const t = vt(this._config?.weather_entity);
    if (!t)
      return null;
    const e = this._state(t);
    if (!e)
      return null;
    const n = String(e.state ?? "").trim();
    if (!n || n === "unavailable" || n === "unknown")
      return null;
    const i = e.attributes ?? {};
    let r = null, o = null;
    const l = i.forecast;
    if (Array.isArray(l) && l.length > 0) {
      const a = l[0];
      if (a && typeof a == "object") {
        const p = a;
        r = this._optionalNumber(p.temperature), o = this._optionalNumber(p.templow);
      }
    }
    return {
      condition: n,
      temperature: this._optionalNumber(i.temperature),
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
      return d`
        <div class="dock">
          <span class="date">${K(this._now, this._timeZone())}</span>
          <span class="divider"></span>
          <span class="clock">${fe(this._now, this._timeZone())}</span>
        </div>
      `;
    const e = xe(t.condition), n = we(t.condition, e), i = t.temperature === null ? g : d`<span class="temp">${Math.round(t.temperature)}°</span>`, r = t.high === null || t.low === null ? null : `${Math.round(t.high)}° / ${Math.round(t.low)}°`;
    return d`
      <div class="dock">
        ${Ne}
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
customElements.define("nestquest-party-board-card", Me);
at({
  type: "nestquest-party-board-card",
  name: "NestQuest Party Board",
  description: "Kids' attract screen for present and away adventurers."
});
const Oe = { CHILD: 2 }, ze = (s) => (...t) => ({ _$litDirective$: s, values: t });
let Pe = class {
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
const { I: Ie } = le, kt = (s) => s, Ct = () => document.createComment(""), P = (s, t, e) => {
  const n = s._$AA.parentNode, i = t === void 0 ? s._$AB : t._$AA;
  if (e === void 0) {
    const r = n.insertBefore(Ct(), i), o = n.insertBefore(Ct(), i);
    e = new Ie(r, o, s, s.options);
  } else {
    const r = e._$AB.nextSibling, o = e._$AM, l = o !== s;
    if (l) {
      let a;
      e._$AQ?.(s), e._$AM = s, e._$AP !== void 0 && (a = s._$AU) !== o._$AU && e._$AP(a);
    }
    if (r !== i || l) {
      let a = e._$AA;
      for (; a !== r; ) {
        const p = kt(a).nextSibling;
        kt(n).insertBefore(a, i), a = p;
      }
    }
  }
  return e;
}, k = (s, t, e = s) => (s._$AI(t, e), s), Le = {}, Ue = (s, t = Le) => s._$AH = t, Re = (s) => s._$AH, X = (s) => {
  s._$AR(), s._$AA.remove();
};
const At = (s, t, e) => {
  const n = /* @__PURE__ */ new Map();
  for (let i = t; i <= e; i++) n.set(s[i], i);
  return n;
}, St = ze(class extends Pe {
  constructor(s) {
    if (super(s), s.type !== Oe.CHILD) throw Error("repeat() can only be used in text expressions");
  }
  dt(s, t, e) {
    let n;
    e === void 0 ? e = t : t !== void 0 && (n = t);
    const i = [], r = [];
    let o = 0;
    for (const l of s) i[o] = n ? n(l, o) : o, r[o] = e(l, o), o++;
    return { values: r, keys: i };
  }
  render(s, t, e) {
    return this.dt(s, t, e).values;
  }
  update(s, [t, e, n]) {
    const i = Re(s), { values: r, keys: o } = this.dt(t, e, n);
    if (!Array.isArray(i)) return this.ut = o, r;
    const l = this.ut ??= [], a = [];
    let p, u, c = 0, f = i.length - 1, h = 0, m = r.length - 1;
    for (; c <= f && h <= m; ) if (i[c] === null) c++;
    else if (i[f] === null) f--;
    else if (l[c] === o[h]) a[h] = k(i[c], r[h]), c++, h++;
    else if (l[f] === o[m]) a[m] = k(i[f], r[m]), f--, m--;
    else if (l[c] === o[m]) a[m] = k(i[c], r[m]), P(s, a[m + 1], i[c]), c++, m--;
    else if (l[f] === o[h]) a[h] = k(i[f], r[h]), P(s, i[c], i[f]), f--, h++;
    else if (p === void 0 && (p = At(o, h, m), u = At(l, c, f)), p.has(l[c])) if (p.has(l[f])) {
      const _ = u.get(o[h]), x = _ !== void 0 ? i[_] : null;
      if (x === null) {
        const j = P(s, i[c]);
        k(j, r[h]), a[h] = j;
      } else a[h] = k(x, r[h]), P(s, i[c], x), i[_] = null;
      h++;
    } else X(i[f]), f--;
    else X(i[c]), c++;
    for (; h <= m; ) {
      const _ = P(s, a[m + 1]);
      k(_, r[h]), a[h++] = _;
    }
    for (; c <= f; ) {
      const _ = i[c++];
      _ !== null && X(_);
    }
    return this.ut = o, Ue(s, a), T;
  }
}), je = [
  "nestquest_quest_completed",
  "nestquest_quest_uncompleted",
  "nestquest_quest_missed",
  "nestquest_child_day_complete"
], Tt = /* @__PURE__ */ new Map();
function M(s, t) {
  const e = `${s ?? "local"}|${JSON.stringify(t)}`, n = Tt.get(e);
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
  return Tt.set(e, i), i;
}
function De(s) {
  const t = s?.config;
  if (!t || typeof t != "object")
    return;
  const e = t.time_zone;
  return typeof e == "string" && e.trim() ? e.trim() : void 0;
}
function D(s, t) {
  return `${M(t, { weekday: "long" }).format(s)}, ${M(t, { month: "short", day: "numeric" }).format(s)}`;
}
function He(s, t) {
  return M(t, { weekday: "long" }).format(s);
}
function Be(s, t) {
  const e = new Date(s);
  return Number.isNaN(e.getTime()) ? "" : M(t, {
    hour: "numeric",
    minute: "2-digit",
    hour12: !0
  }).format(e);
}
function Fe(s, t) {
  return M(t, {
    hour: "numeric",
    minute: "2-digit",
    hour12: !0
  }).format(s);
}
function Qe(s) {
  if (!s)
    return null;
  const t = /^(\d{1,2}):(\d{2})$/.exec(s.trim());
  if (!t)
    return null;
  const e = Number(t[1]);
  if (e > 23)
    return null;
  const n = e >= 12 ? "PM" : "AM";
  return `${e % 12 === 0 ? 12 : e % 12}:${t[2]} ${n}`;
}
function w(s) {
  return typeof s == "string" ? s.trim() : "";
}
function y(s, t) {
  if (s == null || s === "")
    return t;
  const e = typeof s == "number" ? s : Number(s);
  return Number.isFinite(e) ? e : t;
}
function b(s) {
  return Math.max(0, Math.round(s));
}
function Y(s) {
  return s.split(/[-_]+/).filter(Boolean).map((t) => t.charAt(0).toUpperCase() + t.slice(1)).join(" ");
}
function We(s, t) {
  const e = M(t, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23"
  }).formatToParts(new Date(s)), n = (r) => {
    const o = e.find((l) => l.type === r);
    return o ? Number(o.value) : Number.NaN;
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
function Et(s, t) {
  if (typeof s != "string")
    return null;
  const e = s.split("-");
  if (e.length !== 3)
    return null;
  const [n, i, r] = e.map((a) => Number(a));
  if (!n || !i || !r)
    return null;
  if (!t) {
    const a = new Date(n, i - 1, r);
    return Number.isNaN(a.getTime()) ? null : a;
  }
  const o = Date.UTC(n, i - 1, r), l = new Date(o - We(o, t));
  return Number.isNaN(l.getTime()) ? null : l;
}
function Ze() {
  const s = window.location.pathname.split("/").filter(Boolean);
  return s.length > 0 ? s[s.length - 1].toLowerCase() : "";
}
function Ge(s) {
  if (!s || typeof s != "object")
    return null;
  const t = s, e = w(t.state).toLowerCase();
  if (e !== "open" && e !== "completed")
    return null;
  const n = y(t.id, 0);
  if (!n)
    return null;
  const i = y(t.child_id, 0);
  return {
    id: n,
    child_id: i > 0 ? i : null,
    title: w(t.title) || "Quest",
    icon: w(t.icon) || null,
    window: w(t.window).toLowerCase(),
    due_time: w(t.due_time) || null,
    state: e,
    overdue: t.overdue === !0,
    completed_at: w(t.completed_at) || null,
    on_time: t.on_time === !0 ? !0 : t.on_time === !1 ? !1 : null
  };
}
const Ve = {
  "clear-night": "Clear",
  cloudy: "Cloudy",
  exceptional: "Clear",
  fog: "Foggy",
  hail: "Hail",
  lightning: "Storms",
  "lightning-rainy": "Storms",
  partlycloudy: "Partly cloudy",
  pouring: "Heavy rain",
  rainy: "Rain",
  snowy: "Snow",
  "snowy-rainy": "Sleet",
  sunny: "Sunny",
  windy: "Windy",
  "windy-variant": "Windy"
}, Ke = {
  "clear-night": "Clear night skies",
  cloudy: "Grey skies today",
  exceptional: "A striking day",
  fog: "Mist on the road",
  hail: "Ice from the sky",
  lightning: "Storms may roll in",
  "lightning-rainy": "Storms may roll in",
  partlycloudy: "Sun between clouds",
  pouring: "Heavy rain outside",
  rainy: "Rain on the walls",
  snowy: "Snow on the peaks",
  "snowy-rainy": "Sleet may fall",
  sunny: "Clear skies today",
  windy: "A blustery day",
  "windy-variant": "A blustery day"
};
function Je(s) {
  const t = Ve[s];
  return t || s.charAt(0).toUpperCase() + s.slice(1);
}
function Xe(s, t) {
  return Ke[s] ?? t;
}
const Nt = "polygon(0 0, 100% 0, 100% 62%, 50% 100%, 0 62%)", Ye = "polygon(50% 0, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)", Mt = [-9, 6, -4], tn = Pt`
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
    padding: 4px;
    clip-path: ${v(Nt)};
    background: rgba(255, 255, 255, 0.22);
  }

  .crest-face {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-bottom: 32px;
    clip-path: ${v(Nt)};
    background: var(--nq-p-crest);
  }

  .crest .initial {
    font-family: var(--nq-p-font-display);
    font-size: 44px;
    font-weight: 700;
    line-height: 1;
    color: #ffffff;
  }

  .crest.away .crest-face {
    background: var(--nq-p-crest-away);
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
    clip-path: ${v(Ye)};
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

  .notice-wrap {
    position: absolute;
    top: 236px;
    left: var(--nq-p-page-inset);
    right: var(--nq-p-page-inset);
    bottom: 130px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .notice {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 20px;
    width: 100%;
    max-width: 980px;
    padding: 56px 64px;
    border: 2px solid var(--nq-p-panel-border);
    border-radius: 20px;
    background: var(--nq-p-card-panel);
    box-shadow: var(--nq-p-panel-shadow);
    text-align: center;
  }

  .notice svg {
    width: 46px;
    height: 46px;
    color: var(--nq-p-ink-secondary);
  }

  .notice.away {
    background: linear-gradient(#f2ecdd, #e6dcc6);
    border-style: dashed;
    box-shadow: none;
  }

  .notice-headline {
    font-family: var(--nq-p-font-heading);
    font-size: 40px;
    font-weight: 700;
    line-height: 1.15;
    color: var(--nq-p-ink);
  }

  .notice-body {
    margin: 0;
    font-family: var(--nq-p-font-body);
    font-size: 24px;
    font-weight: 600;
    line-height: 1.4;
    color: var(--nq-p-ink-secondary);
  }

  .notice-seal {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 78px;
    height: 78px;
    border-radius: var(--nq-p-radius-pill);
    background: var(--nq-p-seal);
    box-shadow: var(--nq-p-seal-shadow);
    color: rgba(255, 235, 235, 0.95);
    transform: rotate(-6deg);
  }

  .notice-seal svg {
    width: 38px;
    height: 38px;
    color: rgba(255, 235, 235, 0.95);
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

  .toast {
    position: absolute;
    left: 50%;
    bottom: 158px;
    z-index: 20;
    transform: translateX(-50%);
    max-width: calc(100% - 124px);
    padding: 20px 32px;
    border: 2px solid var(--nq-p-panel-border);
    border-radius: 14px;
    background: var(--nq-p-card-panel);
    box-shadow: var(--nq-p-panel-shadow);
    font-family: var(--nq-p-font-body);
    font-size: 23px;
    font-weight: 600;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--nq-p-ink-secondary);
    animation: toast-in var(--nq-dur-base) var(--nq-ease-out);
    pointer-events: none;
  }

  @keyframes toast-in {
    from {
      opacity: 0;
      transform: translate(-50%, 12px);
    }
    to {
      opacity: 1;
      transform: translate(-50%, 0);
    }
  }

  .complete-screen {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 96px 62px 130px;
    text-align: center;
  }

  .complete-seal {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 168px;
    height: 168px;
    border-radius: var(--nq-p-radius-pill);
    background: var(--nq-p-seal);
    box-shadow: 0 10px 24px rgba(60, 10, 20, 0.42);
    color: rgba(255, 235, 235, 0.95);
    transform: rotate(-6deg);
  }

  .complete-seal svg {
    width: 86px;
    height: 86px;
  }

  .complete-title {
    margin: 28px 0 0;
    font-family: var(--nq-p-font-display);
    font-size: 86px;
    font-weight: 900;
    line-height: 1.1;
    background: var(--nq-brand-gradient-h);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    -webkit-text-fill-color: transparent;
  }

  .complete-sub {
    margin: 16px 0 0;
    max-width: 1000px;
    font-family: var(--nq-p-font-body);
    font-size: 34px;
    font-weight: 600;
    line-height: 1.35;
    color: var(--nq-p-ink-secondary);
    text-wrap: pretty;
  }

  .complete-countdown {
    margin: 12px 0 0;
    font-family: var(--nq-p-font-body);
    font-size: 25px;
    font-weight: 600;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
  }

  .complete-stats {
    position: absolute;
    top: 540px;
    left: 200px;
    right: 200px;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 26px;
  }

  .complete-stat {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 28px 16px;
    border: 2px solid var(--nq-p-panel-border);
    border-radius: 16px;
    background: var(--nq-p-card-panel);
    box-shadow: var(--nq-p-panel-shadow);
  }

  .complete-stat .numeral {
    font-family: var(--nq-p-font-heading);
    font-size: 58px;
    font-weight: 900;
    line-height: 1;
    color: var(--nq-p-ink);
  }

  .complete-stat .label {
    font-family: var(--nq-p-font-heading);
    font-size: 17px;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    line-height: 1.2;
    color: var(--nq-p-ink-secondary);
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
`, H = d`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M20 6 9 17l-5-5"></path>
</svg>`, en = d`<svg
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
</svg>`, tt = d`<svg
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
</svg>`, nn = d`<svg
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
</svg>`, Ht = d`<svg
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
</svg>`, sn = d`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path>
</svg>`, rn = d`<svg
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
</svg>`, on = d`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <circle cx="12" cy="12" r="10"></circle>
  <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"></polygon>
</svg>`, an = d`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path>
  <path d="M12 9v4"></path>
  <path d="M12 17h.01"></path>
</svg>`, ln = d`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"></path>
  <path d="m2 2 20 20"></path>
</svg>`, cn = d`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M13 16a3 3 0 1 1 0 6H7a5 5 0 1 1 4.9-6Z"></path>
  <path d="M10.1 9A6 6 0 0 1 16 4a4.5 4.5 0 0 0 8.9 4.2v.1a6 6 0 0 1-5.2 5.7"></path>
</svg>`, dn = {
  icon: on,
  headline: "No adventurer chosen",
  body: "Open The Party and tap your crest to open your quest log."
}, pn = {
  icon: an,
  headline: "NestQuest is not set up yet",
  body: "A parent needs to finish setting up NestQuest."
}, hn = {
  icon: ln,
  headline: "The records cannot be reached",
  body: "The party's records are quiet right now. NestQuest will return shortly."
}, Ot = [
  { key: "morning", name: "Morning", range: "Until 11:59 AM", icon: nn },
  { key: "afternoon", name: "Afternoon", range: "12:00–5:00 PM", icon: Ht },
  { key: "evening", name: "Evening", range: "5:00–9:00 PM", icon: sn }
];
class un extends A {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 },
    _now: { state: !0 },
    _confirm: { state: !0 },
    _optimistic: { state: !0 },
    _toast: { state: !0 },
    _countdown: { state: !0 }
  };
  static styles = [v(Dt), tn];
  hass;
  _config;
  _now = /* @__PURE__ */ new Date();
  _confirm = null;
  /** instanceId → the completion instant stamped before the service has
   *  answered; the seal shows immediately and reverts on failure. */
  _optimistic = /* @__PURE__ */ new Map();
  _toast = null;
  _countdown = null;
  _clockTimer;
  _idleTimer;
  _confirmTimer;
  _toastTimer;
  _completeTimer;
  _unsubs = [];
  _subscribed = !1;
  _subGeneration = 0;
  _retryTimer;
  setConfig(t) {
    if (!t || typeof t != "object")
      throw new Error("Invalid configuration");
    this._config = t;
  }
  _hassConnection() {
    const t = this.hass?.connection;
    return !t || typeof t != "object" || typeof t.subscribeEvents != "function" ? null : t;
  }
  _subscribeLive() {
    if (!this.isConnected || this._subscribed)
      return;
    const t = this._hassConnection();
    if (!t)
      return;
    this._subscribed = !0;
    const e = ++this._subGeneration, n = (i) => {
      i.then((r) => {
        this._subscribed && e === this._subGeneration ? this._unsubs.push(r) : r();
      }).catch(() => {
        e === this._subGeneration && (this._unsubscribeLive(), this._armSubscribeRetry());
      });
    };
    for (const i of je)
      n(
        t.subscribeEvents(() => this.requestUpdate(), i)
      );
  }
  _armSubscribeRetry() {
    this._retryTimer === void 0 && (this._retryTimer = window.setTimeout(() => {
      this._retryTimer = void 0, this._subscribeLive();
    }, 1e3));
  }
  _clearSubscribeRetry() {
    this._retryTimer !== void 0 && (window.clearTimeout(this._retryTimer), this._retryTimer = void 0);
  }
  _unsubscribeLive() {
    this._clearSubscribeRetry(), this._subGeneration++;
    for (const t of this._unsubs)
      t();
    this._unsubs = [], this._subscribed = !1;
  }
  getCardSize() {
    return 22;
  }
  connectedCallback() {
    super.connectedCallback(), this._subscribeLive(), this._now = /* @__PURE__ */ new Date(), this._clockTimer = window.setInterval(() => {
      this._now = /* @__PURE__ */ new Date();
    }, 6e4), window.addEventListener("pointerdown", this._onActivity, !0), window.addEventListener("touchstart", this._onActivity, !0), window.addEventListener("keydown", this._onActivity, !0), this._armIdle(), this._logView().kind === "complete-day" && this._armCompleteTimer();
  }
  updated() {
    this._subscribeLive(), this._logView().kind === "complete-day" ? (this._clearIdle(), this._armCompleteTimer()) : (this._clearCompleteTimer(), this._countdown = null, this._idleTimer === void 0 && this._armIdle());
  }
  disconnectedCallback() {
    this._unsubscribeLive(), this._stopClock(), this._clearIdle(), this._clearConfirmTimer(), this._clearToastTimer(), this._clearCompleteTimer(), window.removeEventListener("pointerdown", this._onActivity, !0), window.removeEventListener("touchstart", this._onActivity, !0), window.removeEventListener("keydown", this._onActivity, !0), super.disconnectedCallback();
  }
  render() {
    const t = this._logView();
    return d`
      <div class="board">
        <div class="frame frame-outer"></div>
        <div class="frame frame-inner"></div>
        ${this._renderMain(t)}
        ${this._renderConfirm()}
        ${this._renderToast()}
      </div>
    `;
  }
  _renderToast() {
    return this._toast === null ? g : d`
      <div class="toast" role="status">${this._toast}</div>
    `;
  }
  _renderMain(t) {
    switch (t.kind) {
      case "no-adventurer":
        return this._renderNotice(dn);
      case "not-set-up":
        return this._renderNotice(pn);
      case "unreachable":
        return this._renderNotice(hn);
      case "away": {
        const e = ["The quest log unlocks when they return."];
        return t.returns && e.push(`Returns ${t.returns}`), d`
          ${this._renderHeader(t)}
          <div class="notice-wrap">
            <div class="notice away" role="status">
              ${rn}
              <span class="notice-headline">${t.name} is on travels</span>
              ${e.map((n) => d`<p class="notice-body">${n}</p>`)}
            </div>
          </div>
        `;
      }
      case "empty-day":
        return d`
          ${this._renderHeader(t)}
          <div class="notice-wrap">
            <div class="notice" role="status">
              ${Ht}
              <span class="notice-headline">No quests today</span>
              <p class="notice-body">
                ${`Nothing was posted for today, ${t.name}. Enjoy the day's rest!`}
              </p>
            </div>
          </div>
        `;
      case "complete-day": {
        const e = this._completeStats(), n = this._countdown ?? this._completeSeconds();
        return d`
          <div class="complete-screen" role="status">
            <span class="complete-seal" aria-hidden="true">${H}</span>
            <h1 class="complete-title">Quest complete</h1>
            <p class="complete-sub">${this._completeSub(t.name)}</p>
            <p class="complete-countdown">
              Returning to The Party in ${n} seconds
            </p>
            <div class="complete-stats">
              <div class="complete-stat">
                <span class="numeral">${e.claimed}</span>
                <span class="label">Quests claimed</span>
              </div>
              <div class="complete-stat">
                <span class="numeral">${e.onTime}</span>
                <span class="label">On time</span>
              </div>
              <div class="complete-stat">
                <span class="numeral">${e.late}</span>
                <span class="label">Late</span>
              </div>
              <div class="complete-stat">
                <span class="numeral">${e.party}</span>
                <span class="label">The Party</span>
              </div>
            </div>
          </div>
          ${this._renderDock()}
        `;
      }
      default:
        return d`
          ${this._renderHeader(t)}
          <div class="columns">
            ${Ot.map((e) => this._renderColumn(e))}
          </div>
        `;
    }
  }
  /** Resolve the log's single render state; the priority order is
   *  design/PANEL-EMPTY-STATES.md §2. */
  _logView() {
    const t = this._childSlug();
    if (!t)
      return { kind: "no-adventurer" };
    const e = this._dueSensorResolution(t);
    if (e === "missing")
      return { kind: "not-set-up" };
    if (e === "stale")
      return { kind: "unreachable" };
    const n = this._childName(t) ?? Y(t);
    if (!this._childPresent(t))
      return { kind: "away", name: n, returns: this._awayReturns(t) };
    const i = this._state(`binary_sensor.nestquest_${t}_all_done`);
    if (i && String(i.state ?? "").trim().toLowerCase() === "on")
      return { kind: "complete-day", name: n };
    const r = this._state(`sensor.nestquest_${t}_quests_due_today`);
    return b(y(r?.state, 0)) === 0 ? { kind: "empty-day", name: n } : this._remaining() === 0 ? { kind: "complete-day", name: n } : { kind: "normal" };
  }
  /** "missing" when the due sensor does not exist (integration not
   *  configured), "stale" when it answers unavailable/unknown (backend
   *  unreachable or the child is absent from the snapshot), null when
   *  it resolves. */
  _dueSensorResolution(t) {
    const e = this._state(`sensor.nestquest_${t}_quests_due_today`);
    if (!e)
      return "missing";
    const n = String(e.state ?? "").trim().toLowerCase();
    return !n || n === "unavailable" || n === "unknown" ? "stale" : null;
  }
  _childPresent(t) {
    const n = this._state(`sensor.nestquest_${t}_quests_due_today`)?.attributes?.present;
    if (typeof n == "boolean")
      return n;
    const i = this._state(
      `binary_sensor.nestquest_${t}_present_today`
    );
    return i ? String(i.state ?? "").trim().toLowerCase() === "on" : !0;
  }
  _awayReturns(t) {
    const e = this._timeZone(), n = this._state(
      `binary_sensor.nestquest_${t}_present_today`
    ), i = Et(
      n?.attributes?.next_present,
      e
    );
    return i ? D(i, e) : null;
  }
  _renderNotice(t) {
    return d`
      <div class="notice-wrap">
        <div class="notice" role="status">
          ${t.icon}
          <span class="notice-headline">${t.headline}</span>
          <p class="notice-body">${t.body}</p>
        </div>
      </div>
    `;
  }
  _timeZone() {
    return De(this.hass);
  }
  _state(t) {
    const n = this.hass?.states?.[t];
    return n && typeof n == "object" ? n : null;
  }
  _childSlug() {
    return Ze();
  }
  _boardPath() {
    return w(this._config?.board_path).replace(/\/+$/, "");
  }
  _idleSeconds() {
    const t = y(this._config?.idle_return_seconds, 40);
    return t > 0 ? t : 40;
  }
  _confirmSeconds() {
    const t = y(this._config?.confirm_timeout_seconds, 15);
    return t > 0 ? t : 15;
  }
  _completeSeconds() {
    const t = y(this._config?.complete_screen_seconds, 12);
    return t > 0 ? t : 12;
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
    ), i = b(y(e?.state, 0)), r = b(y(n?.state, 0));
    return { due: i, completed: r };
  }
  _instances() {
    const t = this._childSlug();
    if (!t)
      return [];
    const e = this._state(`sensor.nestquest_${t}_quests_due_today`)?.attributes?.instances;
    if (!Array.isArray(e))
      return [];
    const n = e.map(Ge).filter((r) => r !== null);
    if (this._optimistic.size === 0)
      return n;
    let i = !1;
    for (const r of n) {
      const o = this._optimistic.get(r.id);
      if (o !== void 0) {
        if (r.state === "completed") {
          this._optimistic.delete(r.id), i = !0;
          continue;
        }
        r.state = "completed", r.overdue = !1, r.completed_at = o;
      }
    }
    return i && (this._optimistic = new Map(this._optimistic)), n;
  }
  _remaining() {
    const t = this._childSlug();
    if (!t)
      return 0;
    const e = this._state(
      `sensor.nestquest_${t}_quests_remaining_today`
    );
    if (e)
      return b(y(e.state, 0));
    const { due: n, completed: i } = this._childCounts(t);
    return b(n - i);
  }
  _partyCounts() {
    const t = this._state(
      "sensor.nestquest_household_quests_due_today"
    ), e = this._state(
      "sensor.nestquest_household_quests_completed_today"
    );
    if (t || e)
      return {
        completed: b(y(e?.state, 0)),
        due: b(y(t?.state, 0))
      };
    const n = this._childSlug(), { due: i, completed: r } = this._childCounts(n);
    return { completed: r, due: i };
  }
  _completeStats() {
    const t = this._childCounts(this._childSlug()).completed, e = this._instances().filter(
      (r) => r.on_time === !0
    ).length, n = b(t - e), i = this._partyCounts();
    return {
      claimed: t,
      onTime: e,
      late: n,
      party: `${i.completed}/${i.due}`
    };
  }
  _completeSub(t) {
    const e = D(this._now, this._timeZone()), { claimed: n, onTime: i, late: r } = this._completeStats();
    return n === 0 ? `${t} sealed the day on ${e}.` : r === 0 ? `${t} claimed every quest on ${e} — all on time.` : i === 0 ? `${t} claimed every quest on ${e} — all late.` : `${t} claimed every quest on ${e} — ${i} on time, ${r} late.`;
  }
  _otherChildren() {
    const t = this.hass?.states;
    if (!t)
      return [];
    const e = this._childSlug(), n = this._timeZone(), i = [];
    for (const r of Object.keys(t)) {
      const o = /^sensor\.nestquest_(.+)_quests_due_today$/.exec(r);
      if (!o || o[1] === "household" || o[1] === e)
        continue;
      const l = o[1], a = t[r]?.attributes ?? {};
      let p = "";
      typeof a.child_name == "string" && a.child_name.trim() ? p = a.child_name.trim() : p = Y(l);
      let u = !0;
      if (typeof a.present == "boolean")
        u = a.present;
      else {
        const _ = this._state(
          `binary_sensor.nestquest_${l}_present_today`
        );
        u = _ === null || String(_.state ?? "").trim().toLowerCase() !== "off";
      }
      const c = this._state(
        `sensor.nestquest_${l}_quests_completed_today`
      ), f = b(y(t[r]?.state, 0)), h = b(y(c?.state, 0));
      let m = null;
      if (!u) {
        const _ = this._state(
          `binary_sensor.nestquest_${l}_present_today`
        ), x = Et(
          _?.attributes?.next_present,
          n
        );
        m = x ? He(x, n) : null;
      }
      i.push({
        slug: l,
        name: p,
        present: u,
        due: f,
        completed: h,
        returnsWeekday: m
      });
    }
    return i.sort((r, o) => r.name.localeCompare(o.name));
  }
  _renderHeader(t) {
    const e = this._childSlug(), n = t.kind === "away", i = n ? t.name : this._childName(e) ?? (e ? Y(e) : null), { due: r, completed: o } = this._childCounts(e), l = this._remaining(), a = this._partyCounts(), p = i ? `${i}'s Quest Log` : "Quest Log", u = (i?.charAt(0) || "?").toUpperCase();
    return d`
      <header class="header">
        <span class="crest${n ? " away" : ""}" aria-hidden="true">
          <span class="crest-face">
            <span class="initial">${u}</span>
          </span>
        </span>
        <div class="titles">
          <h1 class="title">${p}</h1>
          <p class="sub">
            ${D(this._now, this._timeZone())} ·
            ${n ? "On travels" : `${o} of ${r} claimed`}
          </p>
        </div>
        ${n ? g : d`
              <div class="remaining">
                <span class="d20" aria-hidden="true">
                  <span class="d20-numeral">${l}</span>
                </span>
                <div class="remaining-text">
                  <span class="remaining-count">
                    ${l} quest${l === 1 ? "" : "s"} left
                  </span>
                  <span class="party-line">
                    Party progress · ${a.completed} of ${a.due} today
                  </span>
                </div>
              </div>
            `}
      </header>
    `;
  }
  _renderColumn(t) {
    const e = this._instances().filter(
      (l) => l.window === t.key
    ), n = e.filter((l) => l.state === "open").sort(
      (l, a) => (l.due_time ?? "99:99").localeCompare(a.due_time ?? "99:99")
    ), i = e.filter(
      (l) => l.state === "completed"
    ), r = e.length;
    let o = g;
    if (r > 0) {
      const a = 644 - (t.key === "afternoon" && this._otherChildren().length > 0 ? 160 : 0), p = Math.min(
        24,
        Math.max(8, Math.floor((a - r * 74) / Math.max(r - 1, 1)))
      ), u = Math.min(
        116,
        Math.max(58, Math.floor((a - (r - 1) * p) / r))
      ), c = Math.max(56, Math.min(72, u - 2));
      let f = `--nq-p-quest-gap: ${p}px; --nq-p-quest-min-height: ${u}px; --nq-p-button-height: ${c}px`;
      if (r >= 5) {
        const h = Math.max(0, Math.min(22, Math.floor((u - c - 2) / 2))), m = Math.max(44, Math.min(64, u - 2 * h - 2));
        f += `; --nq-p-quest-pad: ${h}px; --nq-p-tile-size: ${m}px`;
      }
      o = f;
    }
    return d`
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
          <span class="column-count">${i.length}/${e.length}</span>
        </div>
        <div class="stack">
          ${St(
      n,
      (l) => l.id,
      (l) => this._renderQuest(l, !1, 0)
    )}
          ${St(
      i,
      (l) => l.id,
      (l, a) => this._renderQuest(l, !0, a)
    )}
          ${t.key === "afternoon" ? this._renderRollup() : g}
        </div>
      </section>
    `;
  }
  _renderQuest(t, e, n) {
    if (e) {
      const o = Mt[n % Mt.length], l = t.completed_at ? Be(t.completed_at, this._timeZone()) : "";
      return d`
        <div class="quest sealed" data-instance-id=${t.id}>
          <span class="tile" aria-hidden="true">${tt}</span>
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
            ${H}
          </span>
        </div>
      `;
    }
    const i = Qe(t.due_time), r = t.overdue ? {
      text: i ? `Overdue · due ${i}` : "Overdue",
      late: !0
    } : {
      text: i ? `Due by ${i}` : "Due today",
      late: !1
    };
    return d`
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
        <span class="tile" aria-hidden="true">${tt}</span>
        <div class="body">
          <span class="quest-title">${t.title}</span>
          <span class="meta ${r.late ? "late" : g}">${r.text}</span>
        </div>
        <button
          class="complete"
          type="button"
          @click=${() => this._openConfirm(t.id)}
        >
          ${H}
          <span>Complete</span>
        </button>
      </div>
    `;
  }
  _renderRollup() {
    const t = this._otherChildren();
    if (t.length === 0)
      return g;
    const e = t.slice(0, 2).map((n) => n.present ? n.due > 0 && n.completed >= n.due ? `${n.name} has finished their log.` : n.due > n.completed ? `${n.name} has ${n.due - n.completed} quests left.` : `${n.name} has no quests today.` : n.returnsWeekday ? `${n.name} is on travels until ${n.returnsWeekday}.` : `${n.name} is on travels.`);
    return d`
      <div class="rollup">
        <span class="rollup-label">Party roll-up</span>
        <p class="rollup-body">${e.join(" ")}</p>
      </div>
    `;
  }
  _renderConfirm() {
    if (this._confirm === null)
      return g;
    const t = this._instances().find(
      (n) => n.id === this._confirm
    );
    if (!t)
      return g;
    const e = Ot.find((n) => n.key === t.window);
    return d`
      <div class="scrim" @click=${() => this._closeConfirm()}>
        <div
          class="dialog"
          role="dialog"
          aria-modal="true"
          @click=${(n) => n.stopPropagation()}
        >
          <div class="dialog-header">
            <span class="dialog-tile" aria-hidden="true">${tt}</span>
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
              ${en}
              <span>Not yet</span>
            </button>
            <button
              class="confirm-button do-complete"
              type="button"
              @click=${() => this._confirmComplete()}
            >
              ${H}
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
    const t = this._confirm === null ? void 0 : this._instances().find(
      (e) => e.id === this._confirm
    );
    this._closeConfirm(), !(!t || t.state !== "open") && this._completeQuest(t);
  }
  /** Seal first, ask the service second: the seal is stamped and the column
   *  re-sorted immediately (PANEL-SPEC §4); a service failure reverts the
   *  card and raises the parchment toast. */
  async _completeQuest(t) {
    if (this._optimistic.has(t.id))
      return;
    const e = (/* @__PURE__ */ new Date()).toISOString();
    this._optimistic = new Map(this._optimistic).set(t.id, e);
    try {
      await this._callCompleteQuest(t);
    } catch {
      const n = new Map(this._optimistic);
      n.delete(t.id), this._optimistic = n, this._showToast(
        "NestQuest could not set the seal just now. Please try again."
      );
    }
  }
  async _callCompleteQuest(t) {
    const e = this.hass;
    if (typeof e?.callService != "function")
      throw new Error("Home Assistant is not connected");
    const n = this._actorChildId(t);
    if (n === null)
      throw new Error("The tapped adventurer is unknown");
    await e.callService.call(e, "nestquest", "complete_quest", {
      instance_id: t.id,
      actor: "panel",
      actor_child_id: n
    });
  }
  /** The tapped profile (decision 9): the instance's own child_id, falling
   *  back to the due sensor's child-level attribute. */
  _actorChildId(t) {
    if (t.child_id !== null)
      return t.child_id;
    const e = this._childSlug(), n = y(
      this._state(`sensor.nestquest_${e}_quests_due_today`)?.attributes?.child_id,
      0
    );
    return n > 0 ? n : null;
  }
  _showToast(t) {
    this._toast = t, this._clearToastTimer(), this._toastTimer = window.setTimeout(() => {
      this._toastTimer = void 0, this._toast = null;
    }, 6e3);
  }
  _clearToastTimer() {
    this._toastTimer !== void 0 && (window.clearTimeout(this._toastTimer), this._toastTimer = void 0);
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
  _armCompleteTimer() {
    if (this._completeTimer === void 0) {
      if (this._countdown === null && (this._countdown = this._completeSeconds()), this._countdown <= 0) {
        this._returnToBoard();
        return;
      }
      this._completeTimer = window.setInterval(() => {
        const t = (this._countdown ?? 1) - 1;
        if (t <= 0) {
          this._countdown = 0, this._clearCompleteTimer(), this._returnToBoard();
          return;
        }
        this._countdown = t;
      }, 1e3);
    }
  }
  _clearCompleteTimer() {
    this._completeTimer !== void 0 && (window.clearInterval(this._completeTimer), this._completeTimer = void 0);
  }
  _optionalNumber(t) {
    if (t == null || t === "")
      return null;
    const e = typeof t == "number" ? t : Number(t);
    return Number.isFinite(e) ? e : null;
  }
  _dockWeather() {
    const t = w(this._config?.weather_entity);
    if (!t)
      return null;
    const e = this._state(t);
    if (!e)
      return null;
    const n = String(e.state ?? "").trim();
    if (!n || n === "unavailable" || n === "unknown")
      return null;
    const i = e.attributes ?? {};
    let r = null, o = null;
    const l = i.forecast;
    if (Array.isArray(l) && l.length > 0) {
      const a = l[0];
      if (a && typeof a == "object") {
        const p = a;
        r = this._optionalNumber(p.temperature), o = this._optionalNumber(p.templow);
      }
    }
    return {
      condition: n,
      temperature: this._optionalNumber(i.temperature),
      high: r,
      low: o
    };
  }
  _renderDock() {
    const t = this._dockWeather();
    if (!t)
      return d`
        <div class="dock">
          <span class="date">${D(this._now, this._timeZone())}</span>
          <span class="divider"></span>
          <span class="clock">${Fe(this._now, this._timeZone())}</span>
        </div>
      `;
    const e = Je(t.condition), n = Xe(t.condition, e), i = t.temperature === null ? g : d`<span class="temp">${Math.round(t.temperature)}°</span>`, r = t.high === null || t.low === null ? null : `${Math.round(t.high)}° / ${Math.round(t.low)}°`;
    return d`
      <div class="dock">
        ${cn}
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
  _returnToBoard() {
    const t = this._boardPath();
    t && (window.history.pushState(null, "", t), window.dispatchEvent(new Event("location-changed")));
  }
  _stopClock() {
    this._clockTimer !== void 0 && (window.clearInterval(this._clockTimer), this._clockTimer = void 0);
  }
  _onActivity = () => {
    this._logView().kind !== "complete-day" && this._armIdle(), this._confirm !== null && this._armConfirmTimer();
  };
}
customElements.define("nestquest-quest-log-card", un);
at({
  type: "nestquest-quest-log-card",
  name: "NestQuest Quest Log",
  description: "One child's daily quests, grouped by window."
});
const fn = ":host{--nq-brand-blue: #3B3AB8;--nq-brand-purple: #A035CC;--nq-brand-gradient: linear-gradient(135deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-brand-gradient-h: linear-gradient(90deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-a-page: #F4F4F6;--nq-a-surface: #FFFFFF;--nq-a-surface-subtle: #FAFAFA;--nq-a-selected: #EBEBF8;--nq-a-border: #E4E4EA;--nq-a-divider: #EDEDF1;--nq-a-ink: #18181D;--nq-a-ink-secondary: #52525E;--nq-a-ink-tertiary: #70707E;--nq-a-success: #15803D;--nq-a-danger: #DC2626;--nq-a-danger-strong: #B91C1C;--nq-a-danger-bg: #FEE2E2;--nq-a-warning-ink: #92400E;--nq-a-warning-ink-2: #78350F;--nq-a-warning-bg: #FEF3C7;--nq-a-warning-border: rgba(217,119,6,.35);--nq-a-info-bg: #DBEAFE;--nq-a-info-ink: #1E3A8A;--nq-a-info-icon: #1D4ED8;--nq-a-reversal: #7D28A0;--nq-a-font: Nunito, system-ui, sans-serif;--nq-a-size-screen: 24px;--nq-a-size-hero: 32px;--nq-a-size-card-title: 19px;--nq-a-size-stat: 22px;--nq-a-size-row: 13.5px;--nq-a-size-meta: 11px;--nq-a-size-label: 10px;--nq-a-track-label: .1em;--nq-a-density-page-pad: 14px 16px 92px;--nq-a-density-gap: 10px;--nq-a-density-card-pad: 13px;--nq-a-density-row-pad: 11px 13px;--nq-a-density-radius: 8px;--nq-a-density-shadow: none;--nq-a-tabbar-height: 70px;--nq-a-tap-min: 44px;--nq-a-radius-pill: 9999px;--nq-a-radius-sheet: 20px 20px 0 0;--nq-a-sheet-shadow: 0 -8px 28px rgba(9,9,11,.18);--nq-a-progress-height: 6px;--nq-ease-out: cubic-bezier(0, 0, .2, 1);--nq-dur-micro: .12s;--nq-dur-base: .2s;--nq-dur-modal: .35s}";
class mn extends A {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 }
  };
  static styles = [v(fn)];
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
    return d`<div>NestQuest Admin</div>`;
  }
}
customElements.define("nestquest-admin-card", mn);
at({
  type: "nestquest-admin-card",
  name: "NestQuest Admin",
  description: "Parent phone view for today, tasks, schedule, and history."
});
function Bt(s) {
  return typeof s == "string" ? s.trim() : "";
}
function gn(s) {
  if (s === null || typeof s != "object" || Array.isArray(s))
    return "";
  const t = s.slug;
  return typeof t == "string" ? t.trim() : "";
}
function _n(s) {
  const t = Bt(s.url_path).replace(/^\/+|\/+$/g, "");
  return t || (window.location.pathname.split("/").filter(Boolean)[0] ?? "");
}
function yn(s) {
  if (s === null || typeof s != "object" || Array.isArray(s))
    return "";
  const t = s.name;
  return typeof t == "string" ? t.trim() : "";
}
function bn(s) {
  const n = s?.states?.["sensor.nestquest_household_quests_due_today"]?.attributes?.child_roster;
  return Array.isArray(n) ? n.map((i) => ({ slug: gn(i), name: yn(i) })).filter((i) => i.slug.length > 0) : [];
}
class vn {
  static async generate(t, e) {
    const n = `/${_n(t)}`, i = Bt(t.weather_entity), r = {
      type: "custom:nestquest-party-board-card",
      quest_log_path: n
    };
    i && (r.weather_entity = i);
    const o = {
      type: "custom:nestquest-quest-log-card",
      board_path: n
    };
    return i && (o.weather_entity = i), {
      views: [
        {
          path: "party",
          title: "The Party",
          type: "panel",
          cards: [r]
        },
        ...bn(e).map((l) => ({
          path: l.slug,
          title: l.name ? `${l.name}'s Quest Log` : `${l.slug}'s Quest Log`,
          type: "panel",
          cards: [{ ...o }]
        }))
      ]
    };
  }
}
window.customStrategies = window.customStrategies ?? {};
window.customStrategies["nestquest-party"] = vn;
const xn = "/nestquest-static/nestquest-fonts.css";
if (!document.querySelector('link[data-nq-fonts=""]')) {
  const s = document.createElement("link");
  s.rel = "stylesheet", s.href = xn, s.dataset.nqFonts = "", document.head.appendChild(s);
}

const L = globalThis, te = L.ShadowRoot && (L.ShadyCSS === void 0 || L.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, ne = /* @__PURE__ */ Symbol(), ae = /* @__PURE__ */ new WeakMap();
let ze = class {
  constructor(e, t, n) {
    if (this._$cssResult$ = !0, n !== ne) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = e, this.t = t;
  }
  get styleSheet() {
    let e = this.o;
    const t = this.t;
    if (te && e === void 0) {
      const n = t !== void 0 && t.length === 1;
      n && (e = ae.get(t)), e === void 0 && ((this.o = e = new CSSStyleSheet()).replaceSync(this.cssText), n && ae.set(t, e));
    }
    return e;
  }
  toString() {
    return this.cssText;
  }
};
const v = (s) => new ze(typeof s == "string" ? s : s + "", void 0, ne), Pe = (s, ...e) => {
  const t = s.length === 1 ? s[0] : e.reduce((n, i, r) => n + ((o) => {
    if (o._$cssResult$ === !0) return o.cssText;
    if (typeof o == "number") return o;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + o + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(i) + s[r + 1], s[0]);
  return new ze(t, s, ne);
}, Be = (s, e) => {
  if (te) s.adoptedStyleSheets = e.map((t) => t instanceof CSSStyleSheet ? t : t.styleSheet);
  else for (const t of e) {
    const n = document.createElement("style"), i = L.litNonce;
    i !== void 0 && n.setAttribute("nonce", i), n.textContent = t.cssText, s.appendChild(n);
  }
}, le = te ? (s) => s : (s) => s instanceof CSSStyleSheet ? ((e) => {
  let t = "";
  for (const n of e.cssRules) t += n.cssText;
  return v(t);
})(s) : s;
const { is: Fe, defineProperty: Qe, getOwnPropertyDescriptor: We, getOwnPropertyNames: Ze, getOwnPropertySymbols: Ve, getPrototypeOf: Ge } = Object, Q = globalThis, de = Q.trustedTypes, Ke = de ? de.emptyScript : "", Je = Q.reactiveElementPolyfillSupport, P = (s, e) => s, ee = { toAttribute(s, e) {
  switch (e) {
    case Boolean:
      s = s ? Ke : null;
      break;
    case Object:
    case Array:
      s = s == null ? s : JSON.stringify(s);
  }
  return s;
}, fromAttribute(s, e) {
  let t = s;
  switch (e) {
    case Boolean:
      t = s !== null;
      break;
    case Number:
      t = s === null ? null : Number(s);
      break;
    case Object:
    case Array:
      try {
        t = JSON.parse(s);
      } catch {
        t = null;
      }
  }
  return t;
} }, Ie = (s, e) => !Fe(s, e), ce = { attribute: !0, type: String, converter: ee, reflect: !1, useDefault: !1, hasChanged: Ie };
Symbol.metadata ??= /* @__PURE__ */ Symbol("metadata"), Q.litPropertyMetadata ??= /* @__PURE__ */ new WeakMap();
let N = class extends HTMLElement {
  static addInitializer(e) {
    this._$Ei(), (this.l ??= []).push(e);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(e, t = ce) {
    if (t.state && (t.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(e) && ((t = Object.create(t)).wrapped = !0), this.elementProperties.set(e, t), !t.noAccessor) {
      const n = /* @__PURE__ */ Symbol(), i = this.getPropertyDescriptor(e, n, t);
      i !== void 0 && Qe(this.prototype, e, i);
    }
  }
  static getPropertyDescriptor(e, t, n) {
    const { get: i, set: r } = We(this.prototype, e) ?? { get() {
      return this[t];
    }, set(o) {
      this[t] = o;
    } };
    return { get: i, set(o) {
      const l = i?.call(this);
      r?.call(this, o), this.requestUpdate(e, l, n);
    }, configurable: !0, enumerable: !0 };
  }
  static getPropertyOptions(e) {
    return this.elementProperties.get(e) ?? ce;
  }
  static _$Ei() {
    if (this.hasOwnProperty(P("elementProperties"))) return;
    const e = Ge(this);
    e.finalize(), e.l !== void 0 && (this.l = [...e.l]), this.elementProperties = new Map(e.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(P("finalized"))) return;
    if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(P("properties"))) {
      const t = this.properties, n = [...Ze(t), ...Ve(t)];
      for (const i of n) this.createProperty(i, t[i]);
    }
    const e = this[Symbol.metadata];
    if (e !== null) {
      const t = litPropertyMetadata.get(e);
      if (t !== void 0) for (const [n, i] of t) this.elementProperties.set(n, i);
    }
    this._$Eh = /* @__PURE__ */ new Map();
    for (const [t, n] of this.elementProperties) {
      const i = this._$Eu(t, n);
      i !== void 0 && this._$Eh.set(i, t);
    }
    this.elementStyles = this.finalizeStyles(this.styles);
  }
  static finalizeStyles(e) {
    const t = [];
    if (Array.isArray(e)) {
      const n = new Set(e.flat(1 / 0).reverse());
      for (const i of n) t.unshift(le(i));
    } else e !== void 0 && t.push(le(e));
    return t;
  }
  static _$Eu(e, t) {
    const n = t.attribute;
    return n === !1 ? void 0 : typeof n == "string" ? n : typeof e == "string" ? e.toLowerCase() : void 0;
  }
  constructor() {
    super(), this._$Ep = void 0, this.isUpdatePending = !1, this.hasUpdated = !1, this._$Em = null, this._$Ev();
  }
  _$Ev() {
    this._$ES = new Promise((e) => this.enableUpdating = e), this._$AL = /* @__PURE__ */ new Map(), this._$E_(), this.requestUpdate(), this.constructor.l?.forEach((e) => e(this));
  }
  addController(e) {
    (this._$EO ??= /* @__PURE__ */ new Set()).add(e), this.renderRoot !== void 0 && this.isConnected && e.hostConnected?.();
  }
  removeController(e) {
    this._$EO?.delete(e);
  }
  _$E_() {
    const e = /* @__PURE__ */ new Map(), t = this.constructor.elementProperties;
    for (const n of t.keys()) this.hasOwnProperty(n) && (e.set(n, this[n]), delete this[n]);
    e.size > 0 && (this._$Ep = e);
  }
  createRenderRoot() {
    const e = this.shadowRoot ?? this.attachShadow(this.constructor.shadowRootOptions);
    return Be(e, this.constructor.elementStyles), e;
  }
  connectedCallback() {
    this.renderRoot ??= this.createRenderRoot(), this.enableUpdating(!0), this._$EO?.forEach((e) => e.hostConnected?.());
  }
  enableUpdating(e) {
  }
  disconnectedCallback() {
    this._$EO?.forEach((e) => e.hostDisconnected?.());
  }
  attributeChangedCallback(e, t, n) {
    this._$AK(e, n);
  }
  _$ET(e, t) {
    const n = this.constructor.elementProperties.get(e), i = this.constructor._$Eu(e, n);
    if (i !== void 0 && n.reflect === !0) {
      const r = (n.converter?.toAttribute !== void 0 ? n.converter : ee).toAttribute(t, n.type);
      this._$Em = e, r == null ? this.removeAttribute(i) : this.setAttribute(i, r), this._$Em = null;
    }
  }
  _$AK(e, t) {
    const n = this.constructor, i = n._$Eh.get(e);
    if (i !== void 0 && this._$Em !== i) {
      const r = n.getPropertyOptions(i), o = typeof r.converter == "function" ? { fromAttribute: r.converter } : r.converter?.fromAttribute !== void 0 ? r.converter : ee;
      this._$Em = i;
      const l = o.fromAttribute(t, r.type);
      this[i] = l ?? this._$Ej?.get(i) ?? l, this._$Em = null;
    }
  }
  requestUpdate(e, t, n, i = !1, r) {
    if (e !== void 0) {
      const o = this.constructor;
      if (i === !1 && (r = this[e]), n ??= o.getPropertyOptions(e), !((n.hasChanged ?? Ie)(r, t) || n.useDefault && n.reflect && r === this._$Ej?.get(e) && !this.hasAttribute(o._$Eu(e, n)))) return;
      this.C(e, t, n);
    }
    this.isUpdatePending === !1 && (this._$ES = this._$EP());
  }
  C(e, t, { useDefault: n, reflect: i, wrapped: r }, o) {
    n && !(this._$Ej ??= /* @__PURE__ */ new Map()).has(e) && (this._$Ej.set(e, o ?? t ?? this[e]), r !== !0 || o !== void 0) || (this._$AL.has(e) || (this.hasUpdated || n || (t = void 0), this._$AL.set(e, t)), i === !0 && this._$Em !== e && (this._$Eq ??= /* @__PURE__ */ new Set()).add(e));
  }
  async _$EP() {
    this.isUpdatePending = !0;
    try {
      await this._$ES;
    } catch (t) {
      Promise.reject(t);
    }
    const e = this.scheduleUpdate();
    return e != null && await e, !this.isUpdatePending;
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
    let e = !1;
    const t = this._$AL;
    try {
      e = this.shouldUpdate(t), e ? (this.willUpdate(t), this._$EO?.forEach((n) => n.hostUpdate?.()), this.update(t)) : this._$EM();
    } catch (n) {
      throw e = !1, this._$EM(), n;
    }
    e && this._$AE(t);
  }
  willUpdate(e) {
  }
  _$AE(e) {
    this._$EO?.forEach((t) => t.hostUpdated?.()), this.hasUpdated || (this.hasUpdated = !0, this.firstUpdated(e)), this.updated(e);
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
  shouldUpdate(e) {
    return !0;
  }
  update(e) {
    this._$Eq &&= this._$Eq.forEach((t) => this._$ET(t, this[t])), this._$EM();
  }
  updated(e) {
  }
  firstUpdated(e) {
  }
};
N.elementStyles = [], N.shadowRootOptions = { mode: "open" }, N[P("elementProperties")] = /* @__PURE__ */ new Map(), N[P("finalized")] = /* @__PURE__ */ new Map(), Je?.({ ReactiveElement: N }), (Q.reactiveElementVersions ??= []).push("2.1.2");
const se = globalThis, pe = (s) => s, B = se.trustedTypes, he = B ? B.createPolicy("lit-html", { createHTML: (s) => s }) : void 0, Ue = "$lit$", x = `lit$${Math.random().toFixed(9).slice(2)}$`, De = "?" + x, Xe = `<${De}>`, S = document, I = () => S.createComment(""), U = (s) => s === null || typeof s != "object" && typeof s != "function", ie = Array.isArray, Ye = (s) => ie(s) || typeof s?.[Symbol.iterator] == "function", V = `[ 	
\f\r]`, O = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, ue = /-->/g, fe = />/g, q = RegExp(`>|${V}(?:([^\\s"'>=/]+)(${V}*=${V}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g"), me = /'/g, ge = /"/g, He = /^(?:script|style|textarea|title)$/i, et = (s) => (e, ...t) => ({ _$litType$: s, strings: e, values: t }), p = et(1), E = /* @__PURE__ */ Symbol.for("lit-noChange"), g = /* @__PURE__ */ Symbol.for("lit-nothing"), ye = /* @__PURE__ */ new WeakMap(), A = S.createTreeWalker(S, 129);
function je(s, e) {
  if (!ie(s) || !s.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return he !== void 0 ? he.createHTML(e) : e;
}
const tt = (s, e) => {
  const t = s.length - 1, n = [];
  let i, r = e === 2 ? "<svg>" : e === 3 ? "<math>" : "", o = O;
  for (let l = 0; l < t; l++) {
    const a = s[l];
    let c, u, d = -1, f = 0;
    for (; f < a.length && (o.lastIndex = f, u = o.exec(a), u !== null); ) f = o.lastIndex, o === O ? u[1] === "!--" ? o = ue : u[1] !== void 0 ? o = fe : u[2] !== void 0 ? (He.test(u[2]) && (i = RegExp("</" + u[2], "g")), o = q) : u[3] !== void 0 && (o = q) : o === q ? u[0] === ">" ? (o = i ?? O, d = -1) : u[1] === void 0 ? d = -2 : (d = o.lastIndex - u[2].length, c = u[1], o = u[3] === void 0 ? q : u[3] === '"' ? ge : me) : o === ge || o === me ? o = q : o === ue || o === fe ? o = O : (o = q, i = void 0);
    const h = o === q && s[l + 1].startsWith("/>") ? " " : "";
    r += o === O ? a + Xe : d >= 0 ? (n.push(c), a.slice(0, d) + Ue + a.slice(d) + x + h) : a + x + (d === -2 ? l : h);
  }
  return [je(s, r + (s[t] || "<?>") + (e === 2 ? "</svg>" : e === 3 ? "</math>" : "")), n];
};
class D {
  constructor({ strings: e, _$litType$: t }, n) {
    let i;
    this.parts = [];
    let r = 0, o = 0;
    const l = e.length - 1, a = this.parts, [c, u] = tt(e, t);
    if (this.el = D.createElement(c, n), A.currentNode = this.el.content, t === 2 || t === 3) {
      const d = this.el.content.firstChild;
      d.replaceWith(...d.childNodes);
    }
    for (; (i = A.nextNode()) !== null && a.length < l; ) {
      if (i.nodeType === 1) {
        if (i.hasAttributes()) for (const d of i.getAttributeNames()) if (d.endsWith(Ue)) {
          const f = u[o++], h = i.getAttribute(d).split(x), m = /([.?@])?(.*)/.exec(f);
          a.push({ type: 1, index: r, name: m[2], strings: h, ctor: m[1] === "." ? st : m[1] === "?" ? it : m[1] === "@" ? rt : W }), i.removeAttribute(d);
        } else d.startsWith(x) && (a.push({ type: 6, index: r }), i.removeAttribute(d));
        if (He.test(i.tagName)) {
          const d = i.textContent.split(x), f = d.length - 1;
          if (f > 0) {
            i.textContent = B ? B.emptyScript : "";
            for (let h = 0; h < f; h++) i.append(d[h], I()), A.nextNode(), a.push({ type: 2, index: ++r });
            i.append(d[f], I());
          }
        }
      } else if (i.nodeType === 8) if (i.data === De) a.push({ type: 2, index: r });
      else {
        let d = -1;
        for (; (d = i.data.indexOf(x, d + 1)) !== -1; ) a.push({ type: 7, index: r }), d += x.length - 1;
      }
      r++;
    }
  }
  static createElement(e, t) {
    const n = S.createElement("template");
    return n.innerHTML = e, n;
  }
}
function T(s, e, t = s, n) {
  if (e === E) return e;
  let i = n !== void 0 ? t._$Co?.[n] : t._$Cl;
  const r = U(e) ? void 0 : e._$litDirective$;
  return i?.constructor !== r && (i?._$AO?.(!1), r === void 0 ? i = void 0 : (i = new r(s), i._$AT(s, t, n)), n !== void 0 ? (t._$Co ??= [])[n] = i : t._$Cl = i), i !== void 0 && (e = T(s, i._$AS(s, e.values), i, n)), e;
}
class nt {
  constructor(e, t) {
    this._$AV = [], this._$AN = void 0, this._$AD = e, this._$AM = t;
  }
  get parentNode() {
    return this._$AM.parentNode;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  u(e) {
    const { el: { content: t }, parts: n } = this._$AD, i = (e?.creationScope ?? S).importNode(t, !0);
    A.currentNode = i;
    let r = A.nextNode(), o = 0, l = 0, a = n[0];
    for (; a !== void 0; ) {
      if (o === a.index) {
        let c;
        a.type === 2 ? c = new M(r, r.nextSibling, this, e) : a.type === 1 ? c = new a.ctor(r, a.name, a.strings, this, e) : a.type === 6 && (c = new ot(r, this, e)), this._$AV.push(c), a = n[++l];
      }
      o !== a?.index && (r = A.nextNode(), o++);
    }
    return A.currentNode = S, i;
  }
  p(e) {
    let t = 0;
    for (const n of this._$AV) n !== void 0 && (n.strings !== void 0 ? (n._$AI(e, n, t), t += n.strings.length - 2) : n._$AI(e[t])), t++;
  }
}
class M {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(e, t, n, i) {
    this.type = 2, this._$AH = g, this._$AN = void 0, this._$AA = e, this._$AB = t, this._$AM = n, this.options = i, this._$Cv = i?.isConnected ?? !0;
  }
  get parentNode() {
    let e = this._$AA.parentNode;
    const t = this._$AM;
    return t !== void 0 && e?.nodeType === 11 && (e = t.parentNode), e;
  }
  get startNode() {
    return this._$AA;
  }
  get endNode() {
    return this._$AB;
  }
  _$AI(e, t = this) {
    e = T(this, e, t), U(e) ? e === g || e == null || e === "" ? (this._$AH !== g && this._$AR(), this._$AH = g) : e !== this._$AH && e !== E && this._(e) : e._$litType$ !== void 0 ? this.$(e) : e.nodeType !== void 0 ? this.T(e) : Ye(e) ? this.k(e) : this._(e);
  }
  O(e) {
    return this._$AA.parentNode.insertBefore(e, this._$AB);
  }
  T(e) {
    this._$AH !== e && (this._$AR(), this._$AH = this.O(e));
  }
  _(e) {
    this._$AH !== g && U(this._$AH) ? this._$AA.nextSibling.data = e : this.T(S.createTextNode(e)), this._$AH = e;
  }
  $(e) {
    const { values: t, _$litType$: n } = e, i = typeof n == "number" ? this._$AC(e) : (n.el === void 0 && (n.el = D.createElement(je(n.h, n.h[0]), this.options)), n);
    if (this._$AH?._$AD === i) this._$AH.p(t);
    else {
      const r = new nt(i, this), o = r.u(this.options);
      r.p(t), this.T(o), this._$AH = r;
    }
  }
  _$AC(e) {
    let t = ye.get(e.strings);
    return t === void 0 && ye.set(e.strings, t = new D(e)), t;
  }
  k(e) {
    ie(this._$AH) || (this._$AH = [], this._$AR());
    const t = this._$AH;
    let n, i = 0;
    for (const r of e) i === t.length ? t.push(n = new M(this.O(I()), this.O(I()), this, this.options)) : n = t[i], n._$AI(r), i++;
    i < t.length && (this._$AR(n && n._$AB.nextSibling, i), t.length = i);
  }
  _$AR(e = this._$AA.nextSibling, t) {
    for (this._$AP?.(!1, !0, t); e !== this._$AB; ) {
      const n = pe(e).nextSibling;
      pe(e).remove(), e = n;
    }
  }
  setConnected(e) {
    this._$AM === void 0 && (this._$Cv = e, this._$AP?.(e));
  }
}
class W {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(e, t, n, i, r) {
    this.type = 1, this._$AH = g, this._$AN = void 0, this.element = e, this.name = t, this._$AM = i, this.options = r, n.length > 2 || n[0] !== "" || n[1] !== "" ? (this._$AH = Array(n.length - 1).fill(new String()), this.strings = n) : this._$AH = g;
  }
  _$AI(e, t = this, n, i) {
    const r = this.strings;
    let o = !1;
    if (r === void 0) e = T(this, e, t, 0), o = !U(e) || e !== this._$AH && e !== E, o && (this._$AH = e);
    else {
      const l = e;
      let a, c;
      for (e = r[0], a = 0; a < r.length - 1; a++) c = T(this, l[n + a], t, a), c === E && (c = this._$AH[a]), o ||= !U(c) || c !== this._$AH[a], c === g ? e = g : e !== g && (e += (c ?? "") + r[a + 1]), this._$AH[a] = c;
    }
    o && !i && this.j(e);
  }
  j(e) {
    e === g ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, e ?? "");
  }
}
class st extends W {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(e) {
    this.element[this.name] = e === g ? void 0 : e;
  }
}
class it extends W {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(e) {
    this.element.toggleAttribute(this.name, !!e && e !== g);
  }
}
class rt extends W {
  constructor(e, t, n, i, r) {
    super(e, t, n, i, r), this.type = 5;
  }
  _$AI(e, t = this) {
    if ((e = T(this, e, t, 0) ?? g) === E) return;
    const n = this._$AH, i = e === g && n !== g || e.capture !== n.capture || e.once !== n.once || e.passive !== n.passive, r = e !== g && (n === g || i);
    i && this.element.removeEventListener(this.name, this, n), r && this.element.addEventListener(this.name, this, e), this._$AH = e;
  }
  handleEvent(e) {
    typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, e) : this._$AH.handleEvent(e);
  }
}
class ot {
  constructor(e, t, n) {
    this.element = e, this.type = 6, this._$AN = void 0, this._$AM = t, this.options = n;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(e) {
    T(this, e);
  }
}
const at = { I: M }, lt = se.litHtmlPolyfillSupport;
lt?.(D, M), (se.litHtmlVersions ??= []).push("3.3.3");
const dt = (s, e, t) => {
  const n = t?.renderBefore ?? e;
  let i = n._$litPart$;
  if (i === void 0) {
    const r = t?.renderBefore ?? null;
    n._$litPart$ = i = new M(e.insertBefore(I(), r), r, void 0, t ?? {});
  }
  return i._$AI(s), i;
};
const re = globalThis;
let C = class extends N {
  constructor() {
    super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
  }
  createRenderRoot() {
    const e = super.createRenderRoot();
    return this.renderOptions.renderBefore ??= e.firstChild, e;
  }
  update(e) {
    const t = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(e), this._$Do = dt(t, this.renderRoot, this.renderOptions);
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
C._$litElement$ = !0, C.finalized = !0, re.litElementHydrateSupport?.({ LitElement: C });
const ct = re.litElementPolyfillSupport;
ct?.({ LitElement: C });
(re.litElementVersions ??= []).push("4.2.2");
const Re = ':host{--nq-p-parchment-top: #f0e4c7;--nq-p-parchment-bottom: #ddcca3;--nq-p-parchment: radial-gradient(ellipse at 25% 10%, rgba(255,255,255,.5), transparent 55%), radial-gradient(ellipse at 85% 90%, rgba(120,86,44,.28), transparent 60%), repeating-linear-gradient(93deg, rgba(150,115,70,.05) 0 2px, transparent 2px 6px), repeating-linear-gradient(2deg, rgba(150,115,70,.04) 0 3px, transparent 3px 7px), linear-gradient(var(--nq-p-parchment-top), var(--nq-p-parchment-bottom));--nq-p-vignette: inset 0 0 200px rgba(80,52,20,.35);--nq-p-card-open: linear-gradient(#fdf7e6, #f2e7c9);--nq-p-card-done: linear-gradient(#f0e8d3, #e6dcc2);--nq-p-card-panel: linear-gradient(#fcf6e6, #f1e6ca);--nq-p-card-border: rgba(120,88,48,.38);--nq-p-panel-border: rgba(92,62,26,.4);--nq-p-card-shadow: 0 3px 0 rgba(120,88,48,.2), inset 0 1px 0 rgba(255,255,255,.7);--nq-p-panel-shadow: 0 6px 0 rgba(92,62,26,.18), inset 0 2px 0 rgba(255,255,255,.7);--nq-p-frame-outer: 2px solid rgba(92,62,26,.45);--nq-p-frame-inner: 1px solid rgba(92,62,26,.28);--nq-p-rule: 2px solid rgba(92,62,26,.35);--nq-p-ink: #2b1f14;--nq-p-ink-secondary: #5c452a;--nq-p-ink-muted: #6f6455;--nq-p-ink-away: #4d4433;--nq-p-ink-late: #8f1526;--nq-brand-blue: #3B3AB8;--nq-brand-purple: #A035CC;--nq-brand-gradient: linear-gradient(135deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-p-icon-tile: var(--nq-brand-gradient);--nq-p-icon-tile-done: rgba(92,62,26,.16);--nq-p-crest: var(--nq-brand-gradient);--nq-p-crest-away: linear-gradient(135deg, #6b6b7a, #7a7286);--nq-p-seal: radial-gradient(circle at 35% 30%, #a8283a, #6d1322);--nq-p-seal-shadow: 0 4px 10px rgba(60,10,20,.4), inset 0 0 0 4px rgba(255,255,255,.14);--nq-p-seal-size: 78px;--nq-p-dock-bg: rgba(43,31,20,.9);--nq-p-dock-ink: #f7efdb;--nq-p-dock-ink-secondary: #d8c9a6;--nq-p-dock-divider: rgba(233,220,189,.3);--nq-p-dock-height: 84px;--nq-p-font-display: "Cinzel Decorative", Cinzel, serif;--nq-p-font-heading: Cinzel, serif;--nq-p-font-body: Nunito, system-ui, sans-serif;--nq-p-size-hero: 86px;--nq-p-size-wordmark: 66px;--nq-p-size-title: 56px;--nq-p-size-name: 48px;--nq-p-size-section: 32px;--nq-p-size-quest: 30px;--nq-p-size-body: 22px;--nq-p-size-label: 21px;--nq-p-track-label: .14em;--nq-p-track-kicker: .3em;--nq-p-quest-min-height: 116px;--nq-p-quest-gap: 24px;--nq-p-quest-pad: 22px;--nq-p-tile-size: 64px;--nq-p-button-height: 72px;--nq-p-button-min-width: 150px;--nq-p-confirm-button: 108px;--nq-p-radius-card: 12px;--nq-p-radius-panel: 20px;--nq-p-radius-pill: 9999px;--nq-p-page-inset: 62px;--nq-p-frame-inset: 26px;--nq-ease-out: cubic-bezier(0, 0, .2, 1);--nq-dur-micro: .12s;--nq-dur-base: .2s;--nq-dur-modal: .35s}';
function oe(s) {
  window.customCards = window.customCards ?? [], window.customCards.push(s);
}
const _e = /* @__PURE__ */ new Map();
function F(s, e) {
  const t = `${s ?? "local"}|${JSON.stringify(e)}`, n = _e.get(t);
  if (n)
    return n;
  let i;
  try {
    i = new Intl.DateTimeFormat("en-US", {
      ...e,
      ...s ? { timeZone: s } : {}
    });
  } catch {
    i = new Intl.DateTimeFormat("en-US", e);
  }
  return _e.set(t, i), i;
}
function pt(s) {
  const e = s?.config;
  if (!e || typeof e != "object")
    return;
  const t = e.time_zone;
  return typeof t == "string" && t.trim() ? t.trim() : void 0;
}
function G(s, e) {
  return `${F(e, { weekday: "long" }).format(s)}, ${F(e, { month: "short", day: "numeric" }).format(s)}`;
}
function ht(s, e) {
  return F(e, {
    hour: "numeric",
    minute: "2-digit",
    hour12: !0
  }).format(s);
}
const ut = {
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
}, ft = {
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
function ve(s) {
  return typeof s == "string" ? s.trim() : "";
}
function K(s, e) {
  if (s == null || s === "")
    return e;
  const t = typeof s == "number" ? s : Number(s);
  return Number.isFinite(t) ? t : e;
}
function be(s) {
  return Number.isFinite(s) ? Math.min(100, Math.max(0, s)) : 0;
}
function $e(s) {
  return Math.max(0, Math.round(s));
}
function mt(s) {
  return s.split(/[-_]+/).filter(Boolean).map((e) => e.charAt(0).toUpperCase() + e.slice(1)).join(" ");
}
function gt(s, e) {
  const t = F(e, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23"
  }).formatToParts(new Date(s)), n = (r) => {
    const o = t.find((l) => l.type === r);
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
function yt(s, e) {
  if (typeof s != "string")
    return null;
  const t = s.split("-");
  if (t.length !== 3)
    return null;
  const [n, i, r] = t.map((a) => Number(a));
  if (!n || !i || !r)
    return null;
  if (!e) {
    const a = new Date(n, i - 1, r);
    return Number.isNaN(a.getTime()) ? null : a;
  }
  const o = Date.UTC(n, i - 1, r), l = new Date(o - gt(o, e));
  return Number.isNaN(l.getTime()) ? null : l;
}
function _t(s) {
  const e = ut[s];
  return e || s.charAt(0).toUpperCase() + s.slice(1);
}
function vt(s, e) {
  return ft[s] ?? e;
}
const xe = "polygon(0 0, 100% 0, 100% 62%, 50% 100%, 0 62%)", bt = "polygon(50% 0, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)", $t = Pe`
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
    clip-path: ${v(bt)};
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
    clip-path: ${v(xe)};
    background: rgba(255, 255, 255, 0.22);
  }

  .crest-face {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-bottom: 70px;
    clip-path: ${v(xe)};
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
`, xt = p`<svg
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
</svg>`, qt = p`<svg
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
</svg>`, wt = p`<svg
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
</svg>`, kt = p`<svg
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
</svg>`, At = p`<svg
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
</svg>`, qe = {
  icon: kt,
  headline: "NestQuest is not set up yet",
  body: "A parent needs to finish setting up NestQuest before the party can gather."
}, Ct = {
  icon: At,
  headline: "The records cannot be reached",
  body: "The party's records are quiet right now. NestQuest will return shortly."
}, St = p`<svg
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
class Et extends C {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 },
    _now: { state: !0 }
  };
  static styles = [v(Re), $t];
  hass;
  _config;
  _now = /* @__PURE__ */ new Date();
  _clockTimer;
  setConfig(e) {
    if (!e || typeof e != "object")
      throw new Error("Invalid configuration");
    this._config = e;
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
    const e = this._boardNotice();
    return p`
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
        <p class="kicker">The Party · ${G(this._now, this._timeZone())}</p>
        ${e ? this._renderNotice(e) : p`
              <div class="plates">
                ${this._plates().map((t) => this._renderPlate(t))}
              </div>
              <p class="hint">Tap your crest to open your Quest Log</p>
            `}
        <div class="spacer"></div>
        ${this._renderDock()}
      </div>
    `;
  }
  _timeZone() {
    return pt(this.hass);
  }
  _state(e) {
    const n = this.hass?.states?.[e];
    return n && typeof n == "object" ? n : null;
  }
  _childSlugs() {
    if (!this._config)
      return [];
    const e = this._config.child_order;
    return Array.isArray(e) ? e.filter(
      (t) => typeof t == "string" && t.trim().length > 0
    ).map((t) => t.trim()) : [];
  }
  _plates() {
    return this._childSlugs().map((e) => this._plate(e));
  }
  _plate(e) {
    const t = this._dueSensorResolution(e), n = this._state(`sensor.nestquest_${e}_quests_due_today`), i = this._state(
      `sensor.nestquest_${e}_quests_completed_today`
    ), r = this._state(
      `sensor.nestquest_${e}_completion_pct_today`
    ), o = this._state(
      `binary_sensor.nestquest_${e}_present_today`
    ), l = n?.attributes ?? {}, a = $e(K(n?.state, 0)), c = $e(K(i?.state, 0)), u = r ? K(r.state, Number.NaN) : Number.NaN, d = Number.isFinite(u) ? be(u) : a > 0 ? be(c / a * 100) : 0;
    let f = !0;
    const h = l.present;
    typeof h == "boolean" ? f = h : o && (f = String(o.state ?? "").trim().toLowerCase() === "on");
    let m = "";
    const y = l.child_name;
    if (typeof y == "string" && y.trim())
      m = y.trim();
    else {
      const Z = o?.attributes?.child_name;
      typeof Z == "string" && Z.trim() && (m = Z.trim());
    }
    m || (m = mt(e));
    const b = yt(
      o?.attributes?.next_present,
      this._timeZone()
    ), j = b ? `Returns ${G(b, this._timeZone())}` : null;
    return {
      slug: e,
      name: m,
      initial: (m.charAt(0) || "?").toUpperCase(),
      present: t === null ? f : !1,
      completed: c,
      due: a,
      pct: d,
      returns: j,
      unresolved: t
    };
  }
  /** "missing" when the due sensor does not exist (integration not
   *  configured), "stale" when it answers unavailable/unknown (backend
   *  unreachable or the child is absent from the snapshot), null when
   *  it resolves. */
  _dueSensorResolution(e) {
    const t = this._state(`sensor.nestquest_${e}_quests_due_today`);
    if (!t)
      return "missing";
    const n = String(t.state ?? "").trim().toLowerCase();
    return !n || n === "unavailable" || n === "unknown" ? "stale" : null;
  }
  _boardNotice() {
    const e = this._plates();
    return e.length === 0 ? qe : e.every((t) => t.unresolved !== null) ? e.some((t) => t.unresolved === "stale") ? Ct : qe : null;
  }
  _renderNotice(e) {
    return p`
      <div class="notice-wrap">
        <div class="notice" role="status">
          ${e.icon}
          <span class="notice-headline">${e.headline}</span>
          <p class="notice-body">${e.body}</p>
        </div>
      </div>
    `;
  }
  _renderPlate(e) {
    return e.unresolved ? p`
        <div class="plate unknown">
          <span class="crest away">
            <span class="crest-face">
              <span class="initial">${e.initial}</span>
            </span>
          </span>
          <span class="name">${e.name}</span>
          <span class="pill away">
            ${wt}
            <span>Unknown</span>
          </span>
          <span class="progress-line">&mdash;</span>
          <span class="bar"></span>
        </div>
      ` : e.present ? p`
        <button
          class="plate"
          type="button"
          aria-label="Open ${e.name}'s Quest Log"
          @click=${() => this._openQuestLog(e.slug)}
        >
          <span class="crest">
            <span class="crest-face">
              <span class="initial">${e.initial}</span>
            </span>
          </span>
          <span class="name">${e.name}</span>
          <span class="pill">
            ${xt}
            <span>Home today</span>
          </span>
          <span class="progress-line">
            ${e.completed} of ${e.due} quests claimed
          </span>
          <span class="bar">
            <span class="fill" style="width: ${e.pct}%"></span>
          </span>
        </button>
      ` : p`
      <div class="plate away">
        <span class="crest away">
          <span class="crest-face">
            <span class="initial">${e.initial}</span>
          </span>
        </span>
        <span class="name">${e.name}</span>
        <span class="pill away">
          ${qt}
          <span>On travels</span>
        </span>
        <span class="progress-line">${e.returns ?? "Returns —"}</span>
        <span class="bar"></span>
      </div>
    `;
  }
  _openQuestLog(e) {
    const t = ve(this._config?.quest_log_path);
    t && (window.history.pushState(null, "", `${t.replace(/\/+$/, "")}/${e}`), window.dispatchEvent(new Event("location-changed")));
  }
  _dockWeather() {
    const e = ve(this._config?.weather_entity);
    if (!e)
      return null;
    const t = this._state(e);
    if (!t)
      return null;
    const n = String(t.state ?? "").trim();
    if (!n || n === "unavailable" || n === "unknown")
      return null;
    const i = t.attributes ?? {};
    let r = null, o = null;
    const l = i.forecast;
    if (Array.isArray(l) && l.length > 0) {
      const a = l[0];
      if (a && typeof a == "object") {
        const c = a;
        r = this._optionalNumber(c.temperature), o = this._optionalNumber(c.templow);
      }
    }
    return {
      condition: n,
      temperature: this._optionalNumber(i.temperature),
      high: r,
      low: o
    };
  }
  _optionalNumber(e) {
    if (e == null || e === "")
      return null;
    const t = typeof e == "number" ? e : Number(e);
    return Number.isFinite(t) ? t : null;
  }
  _renderDock() {
    const e = this._dockWeather();
    if (!e)
      return p`
        <div class="dock">
          <span class="date">${G(this._now, this._timeZone())}</span>
          <span class="divider"></span>
          <span class="clock">${ht(this._now, this._timeZone())}</span>
        </div>
      `;
    const t = _t(e.condition), n = vt(e.condition, t), i = e.temperature === null ? g : p`<span class="temp">${Math.round(e.temperature)}°</span>`, r = e.high === null || e.low === null ? null : `${Math.round(e.high)}° / ${Math.round(e.low)}°`;
    return p`
      <div class="dock">
        ${St}
        ${i}
        <span class="divider"></span>
        <span class="condition">
          ${r === null ? t : `${t} · ${r}`}
        </span>
        <span class="divider"></span>
        <span class="condition">${n}</span>
      </div>
    `;
  }
}
customElements.define("nestquest-party-board-card", Et);
oe({
  type: "nestquest-party-board-card",
  name: "NestQuest Party Board",
  description: "Kids' attract screen for present and away adventurers."
});
const Nt = { CHILD: 2 }, Tt = (s) => (...e) => ({ _$litDirective$: s, values: e });
let Mt = class {
  constructor(e) {
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AT(e, t, n) {
    this._$Ct = e, this._$AM = t, this._$Ci = n;
  }
  _$AS(e, t) {
    return this.update(e, t);
  }
  update(e, t) {
    return this.render(...t);
  }
};
const { I: Ot } = at, we = (s) => s, ke = () => document.createComment(""), z = (s, e, t) => {
  const n = s._$AA.parentNode, i = e === void 0 ? s._$AB : e._$AA;
  if (t === void 0) {
    const r = n.insertBefore(ke(), i), o = n.insertBefore(ke(), i);
    t = new Ot(r, o, s, s.options);
  } else {
    const r = t._$AB.nextSibling, o = t._$AM, l = o !== s;
    if (l) {
      let a;
      t._$AQ?.(s), t._$AM = s, t._$AP !== void 0 && (a = s._$AU) !== o._$AU && t._$AP(a);
    }
    if (r !== i || l) {
      let a = t._$AA;
      for (; a !== r; ) {
        const c = we(a).nextSibling;
        we(n).insertBefore(a, i), a = c;
      }
    }
  }
  return t;
}, w = (s, e, t = s) => (s._$AI(e, t), s), zt = {}, Pt = (s, e = zt) => s._$AH = e, It = (s) => s._$AH, J = (s) => {
  s._$AR(), s._$AA.remove();
};
const Ae = (s, e, t) => {
  const n = /* @__PURE__ */ new Map();
  for (let i = e; i <= t; i++) n.set(s[i], i);
  return n;
}, Ce = Tt(class extends Mt {
  constructor(s) {
    if (super(s), s.type !== Nt.CHILD) throw Error("repeat() can only be used in text expressions");
  }
  dt(s, e, t) {
    let n;
    t === void 0 ? t = e : e !== void 0 && (n = e);
    const i = [], r = [];
    let o = 0;
    for (const l of s) i[o] = n ? n(l, o) : o, r[o] = t(l, o), o++;
    return { values: r, keys: i };
  }
  render(s, e, t) {
    return this.dt(s, e, t).values;
  }
  update(s, [e, t, n]) {
    const i = It(s), { values: r, keys: o } = this.dt(e, t, n);
    if (!Array.isArray(i)) return this.ut = o, r;
    const l = this.ut ??= [], a = [];
    let c, u, d = 0, f = i.length - 1, h = 0, m = r.length - 1;
    for (; d <= f && h <= m; ) if (i[d] === null) d++;
    else if (i[f] === null) f--;
    else if (l[d] === o[h]) a[h] = w(i[d], r[h]), d++, h++;
    else if (l[f] === o[m]) a[m] = w(i[f], r[m]), f--, m--;
    else if (l[d] === o[m]) a[m] = w(i[d], r[m]), z(s, a[m + 1], i[d]), d++, m--;
    else if (l[f] === o[h]) a[h] = w(i[f], r[h]), z(s, i[d], i[f]), f--, h++;
    else if (c === void 0 && (c = Ae(o, h, m), u = Ae(l, d, f)), c.has(l[d])) if (c.has(l[f])) {
      const y = u.get(o[h]), b = y !== void 0 ? i[y] : null;
      if (b === null) {
        const j = z(s, i[d]);
        w(j, r[h]), a[h] = j;
      } else a[h] = w(b, r[h]), z(s, i[d], b), i[y] = null;
      h++;
    } else J(i[f]), f--;
    else J(i[d]), d++;
    for (; h <= m; ) {
      const y = z(s, a[m + 1]);
      w(y, r[h]), a[h++] = y;
    }
    for (; d <= f; ) {
      const y = i[d++];
      y !== null && J(y);
    }
    return this.ut = o, Pt(s, a), E;
  }
}), Se = /* @__PURE__ */ new Map();
function H(s, e) {
  const t = `${s ?? "local"}|${JSON.stringify(e)}`, n = Se.get(t);
  if (n)
    return n;
  let i;
  try {
    i = new Intl.DateTimeFormat("en-US", {
      ...e,
      ...s ? { timeZone: s } : {}
    });
  } catch {
    i = new Intl.DateTimeFormat("en-US", e);
  }
  return Se.set(t, i), i;
}
function Ut(s) {
  const e = s?.config;
  if (!e || typeof e != "object")
    return;
  const t = e.time_zone;
  return typeof t == "string" && t.trim() ? t.trim() : void 0;
}
function Ee(s, e) {
  return `${H(e, { weekday: "long" }).format(s)}, ${H(e, { month: "short", day: "numeric" }).format(s)}`;
}
function Dt(s, e) {
  return H(e, { weekday: "long" }).format(s);
}
function Ht(s, e) {
  const t = new Date(s);
  return Number.isNaN(t.getTime()) ? "" : H(e, {
    hour: "numeric",
    minute: "2-digit",
    hour12: !0
  }).format(t);
}
function jt(s) {
  if (!s)
    return null;
  const e = /^(\d{1,2}):(\d{2})$/.exec(s.trim());
  if (!e)
    return null;
  const t = Number(e[1]);
  if (t > 23)
    return null;
  const n = t >= 12 ? "PM" : "AM";
  return `${t % 12 === 0 ? 12 : t % 12}:${e[2]} ${n}`;
}
function k(s) {
  return typeof s == "string" ? s.trim() : "";
}
function _(s, e) {
  if (s == null || s === "")
    return e;
  const t = typeof s == "number" ? s : Number(s);
  return Number.isFinite(t) ? t : e;
}
function $(s) {
  return Math.max(0, Math.round(s));
}
function X(s) {
  return s.split(/[-_]+/).filter(Boolean).map((e) => e.charAt(0).toUpperCase() + e.slice(1)).join(" ");
}
function Rt(s, e) {
  const t = H(e, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23"
  }).formatToParts(new Date(s)), n = (r) => {
    const o = t.find((l) => l.type === r);
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
function Ne(s, e) {
  if (typeof s != "string")
    return null;
  const t = s.split("-");
  if (t.length !== 3)
    return null;
  const [n, i, r] = t.map((a) => Number(a));
  if (!n || !i || !r)
    return null;
  if (!e) {
    const a = new Date(n, i - 1, r);
    return Number.isNaN(a.getTime()) ? null : a;
  }
  const o = Date.UTC(n, i - 1, r), l = new Date(o - Rt(o, e));
  return Number.isNaN(l.getTime()) ? null : l;
}
function Lt() {
  const s = window.location.pathname.split("/").filter(Boolean);
  return s.length > 0 ? s[s.length - 1].toLowerCase() : "";
}
function Bt(s) {
  if (!s || typeof s != "object")
    return null;
  const e = s, t = k(e.state).toLowerCase();
  if (t !== "open" && t !== "completed")
    return null;
  const n = _(e.id, 0);
  return n ? {
    id: n,
    title: k(e.title) || "Quest",
    icon: k(e.icon) || null,
    window: k(e.window).toLowerCase(),
    due_time: k(e.due_time) || null,
    state: t,
    overdue: e.overdue === !0,
    completed_at: k(e.completed_at) || null
  } : null;
}
const Te = "polygon(0 0, 100% 0, 100% 62%, 50% 100%, 0 62%)", Ft = "polygon(50% 0, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)", Me = [-9, 6, -4], Qt = Pe`
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
    clip-path: ${v(Te)};
    background: rgba(255, 255, 255, 0.22);
  }

  .crest-face {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-bottom: 32px;
    clip-path: ${v(Te)};
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
    clip-path: ${v(Ft)};
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
`, R = p`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M20 6 9 17l-5-5"></path>
</svg>`, Wt = p`<svg
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
</svg>`, Y = p`<svg
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
</svg>`, Zt = p`<svg
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
</svg>`, Le = p`<svg
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
</svg>`, Vt = p`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path>
</svg>`, Gt = p`<svg
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
</svg>`, Kt = p`<svg
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
</svg>`, Jt = p`<svg
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
</svg>`, Xt = p`<svg
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
</svg>`, Yt = {
  icon: Kt,
  headline: "No adventurer chosen",
  body: "Open The Party and tap your crest to open your quest log."
}, en = {
  icon: Jt,
  headline: "NestQuest is not set up yet",
  body: "A parent needs to finish setting up NestQuest."
}, tn = {
  icon: Xt,
  headline: "The records cannot be reached",
  body: "The party's records are quiet right now. NestQuest will return shortly."
}, Oe = [
  { key: "morning", name: "Morning", range: "Until 11:59 AM", icon: Zt },
  { key: "afternoon", name: "Afternoon", range: "12:00–5:00 PM", icon: Le },
  { key: "evening", name: "Evening", range: "5:00–9:00 PM", icon: Vt }
];
class nn extends C {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 },
    _now: { state: !0 },
    _confirm: { state: !0 }
  };
  static styles = [v(Re), Qt];
  hass;
  _config;
  _now = /* @__PURE__ */ new Date();
  _confirm = null;
  _clockTimer;
  _idleTimer;
  _confirmTimer;
  setConfig(e) {
    if (!e || typeof e != "object")
      throw new Error("Invalid configuration");
    this._config = e;
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
    const e = this._logView();
    return p`
      <div class="board">
        <div class="frame frame-outer"></div>
        <div class="frame frame-inner"></div>
        ${this._renderMain(e)}
        ${this._renderConfirm()}
      </div>
    `;
  }
  _renderMain(e) {
    switch (e.kind) {
      case "no-adventurer":
        return this._renderNotice(Yt);
      case "not-set-up":
        return this._renderNotice(en);
      case "unreachable":
        return this._renderNotice(tn);
      case "away": {
        const t = ["The quest log unlocks when they return."];
        return e.returns && t.push(`Returns ${e.returns}`), p`
          ${this._renderHeader(e)}
          <div class="notice-wrap">
            <div class="notice away" role="status">
              ${Gt}
              <span class="notice-headline">${e.name} is on travels</span>
              ${t.map((n) => p`<p class="notice-body">${n}</p>`)}
            </div>
          </div>
        `;
      }
      case "empty-day":
        return p`
          ${this._renderHeader(e)}
          <div class="notice-wrap">
            <div class="notice" role="status">
              ${Le}
              <span class="notice-headline">No quests today</span>
              <p class="notice-body">
                ${`Nothing was posted for today, ${e.name}. Enjoy the day's rest!`}
              </p>
            </div>
          </div>
        `;
      case "complete-day":
        return p`
          ${this._renderHeader(e)}
          <div class="notice-wrap">
            <div class="notice" role="status">
              <span class="notice-seal">${R}</span>
              <span class="notice-headline">Quest complete</span>
              <p class="notice-body">
                ${`Every quest is claimed, ${e.name}. The seal is set for today.`}
              </p>
              <p class="notice-body">Returning to The Party shortly.</p>
            </div>
          </div>
        `;
      default:
        return p`
          ${this._renderHeader(e)}
          <div class="columns">
            ${Oe.map((t) => this._renderColumn(t))}
          </div>
        `;
    }
  }
  /** Resolve the log's single render state; the priority order is
   *  design/PANEL-EMPTY-STATES.md §2. */
  _logView() {
    const e = this._childSlug();
    if (!e)
      return { kind: "no-adventurer" };
    const t = this._dueSensorResolution(e);
    if (t === "missing")
      return { kind: "not-set-up" };
    if (t === "stale")
      return { kind: "unreachable" };
    const n = this._childName(e) ?? X(e);
    if (!this._childPresent(e))
      return { kind: "away", name: n, returns: this._awayReturns(e) };
    const i = this._state(`sensor.nestquest_${e}_quests_due_today`);
    return $(_(i?.state, 0)) === 0 ? { kind: "empty-day", name: n } : this._remaining() === 0 ? { kind: "complete-day", name: n } : { kind: "normal" };
  }
  /** "missing" when the due sensor does not exist (integration not
   *  configured), "stale" when it answers unavailable/unknown (backend
   *  unreachable or the child is absent from the snapshot), null when
   *  it resolves. */
  _dueSensorResolution(e) {
    const t = this._state(`sensor.nestquest_${e}_quests_due_today`);
    if (!t)
      return "missing";
    const n = String(t.state ?? "").trim().toLowerCase();
    return !n || n === "unavailable" || n === "unknown" ? "stale" : null;
  }
  _childPresent(e) {
    const n = this._state(`sensor.nestquest_${e}_quests_due_today`)?.attributes?.present;
    if (typeof n == "boolean")
      return n;
    const i = this._state(
      `binary_sensor.nestquest_${e}_present_today`
    );
    return i ? String(i.state ?? "").trim().toLowerCase() === "on" : !0;
  }
  _awayReturns(e) {
    const t = this._timeZone(), n = this._state(
      `binary_sensor.nestquest_${e}_present_today`
    ), i = Ne(
      n?.attributes?.next_present,
      t
    );
    return i ? Ee(i, t) : null;
  }
  _renderNotice(e) {
    return p`
      <div class="notice-wrap">
        <div class="notice" role="status">
          ${e.icon}
          <span class="notice-headline">${e.headline}</span>
          <p class="notice-body">${e.body}</p>
        </div>
      </div>
    `;
  }
  _timeZone() {
    return Ut(this.hass);
  }
  _state(e) {
    const n = this.hass?.states?.[e];
    return n && typeof n == "object" ? n : null;
  }
  _childSlug() {
    return Lt();
  }
  _boardPath() {
    return k(this._config?.board_path).replace(/\/+$/, "");
  }
  _idleSeconds() {
    const e = _(this._config?.idle_return_seconds, 40);
    return e > 0 ? e : 40;
  }
  _confirmSeconds() {
    const e = _(this._config?.confirm_timeout_seconds, 15);
    return e > 0 ? e : 15;
  }
  _childName(e) {
    if (!e)
      return null;
    const t = this._state(`sensor.nestquest_${e}_quests_due_today`)?.attributes?.child_name;
    return typeof t == "string" && t.trim() ? t.trim() : null;
  }
  _childCounts(e) {
    const t = this._state(`sensor.nestquest_${e}_quests_due_today`), n = this._state(
      `sensor.nestquest_${e}_quests_completed_today`
    ), i = $(_(t?.state, 0)), r = $(_(n?.state, 0));
    return { due: i, completed: r };
  }
  _instances() {
    const e = this._childSlug();
    if (!e)
      return [];
    const t = this._state(`sensor.nestquest_${e}_quests_due_today`)?.attributes?.instances;
    return Array.isArray(t) ? t.map(Bt).filter((n) => n !== null) : [];
  }
  _remaining() {
    const e = this._childSlug();
    if (!e)
      return 0;
    const t = this._state(
      `sensor.nestquest_${e}_quests_remaining_today`
    );
    if (t)
      return $(_(t.state, 0));
    const { due: n, completed: i } = this._childCounts(e);
    return $(n - i);
  }
  _partyCounts() {
    const e = this._state(
      "sensor.nestquest_household_quests_due_today"
    ), t = this._state(
      "sensor.nestquest_household_quests_completed_today"
    );
    if (e || t)
      return {
        completed: $(_(t?.state, 0)),
        due: $(_(e?.state, 0))
      };
    const n = this._childSlug(), { due: i, completed: r } = this._childCounts(n);
    return { completed: r, due: i };
  }
  _otherChildren() {
    const e = this.hass?.states;
    if (!e)
      return [];
    const t = this._childSlug(), n = this._timeZone(), i = [];
    for (const r of Object.keys(e)) {
      const o = /^sensor\.nestquest_(.+)_quests_due_today$/.exec(r);
      if (!o || o[1] === "household" || o[1] === t)
        continue;
      const l = o[1], a = e[r]?.attributes ?? {};
      let c = "";
      typeof a.child_name == "string" && a.child_name.trim() ? c = a.child_name.trim() : c = X(l);
      let u = !0;
      if (typeof a.present == "boolean")
        u = a.present;
      else {
        const y = this._state(
          `binary_sensor.nestquest_${l}_present_today`
        );
        u = y === null || String(y.state ?? "").trim().toLowerCase() !== "off";
      }
      const d = this._state(
        `sensor.nestquest_${l}_quests_completed_today`
      ), f = $(_(e[r]?.state, 0)), h = $(_(d?.state, 0));
      let m = null;
      if (!u) {
        const y = this._state(
          `binary_sensor.nestquest_${l}_present_today`
        ), b = Ne(
          y?.attributes?.next_present,
          n
        );
        m = b ? Dt(b, n) : null;
      }
      i.push({
        slug: l,
        name: c,
        present: u,
        due: f,
        completed: h,
        returnsWeekday: m
      });
    }
    return i.sort((r, o) => r.name.localeCompare(o.name));
  }
  _renderHeader(e) {
    const t = this._childSlug(), n = e.kind === "away", i = n ? e.name : this._childName(t) ?? (t ? X(t) : null), { due: r, completed: o } = this._childCounts(t), l = this._remaining(), a = this._partyCounts(), c = i ? `${i}'s Quest Log` : "Quest Log", u = (i?.charAt(0) || "?").toUpperCase();
    return p`
      <header class="header">
        <span class="crest${n ? " away" : g}" aria-hidden="true">
          <span class="crest-face">
            <span class="initial">${u}</span>
          </span>
        </span>
        <div class="titles">
          <h1 class="title">${c}</h1>
          <p class="sub">
            ${Ee(this._now, this._timeZone())} ·
            ${n ? "On travels" : `${o} of ${r} claimed`}
          </p>
        </div>
        ${n ? g : p`
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
  _renderColumn(e) {
    const t = this._instances().filter(
      (l) => l.window === e.key
    ), n = t.filter((l) => l.state === "open").sort(
      (l, a) => (l.due_time ?? "99:99").localeCompare(a.due_time ?? "99:99")
    ), i = t.filter(
      (l) => l.state === "completed"
    ), r = t.length;
    let o = g;
    if (r > 0) {
      const a = 644 - (e.key === "afternoon" && this._otherChildren().length > 0 ? 160 : 0), c = Math.min(
        24,
        Math.max(8, Math.floor((a - r * 74) / Math.max(r - 1, 1)))
      ), u = Math.min(
        116,
        Math.max(58, Math.floor((a - (r - 1) * c) / r))
      ), d = Math.max(56, Math.min(72, u - 2));
      let f = `--nq-p-quest-gap: ${c}px; --nq-p-quest-min-height: ${u}px; --nq-p-button-height: ${d}px`;
      if (r >= 5) {
        const h = Math.max(0, Math.min(22, Math.floor((u - d - 2) / 2))), m = Math.max(44, Math.min(64, u - 2 * h - 2));
        f += `; --nq-p-quest-pad: ${h}px; --nq-p-tile-size: ${m}px`;
      }
      o = f;
    }
    return p`
      <section
        class="column"
        aria-label="${e.name} quests"
        style=${o}
      >
        <div class="column-head">
          ${e.icon}
          <div class="column-names">
            <span class="column-name">${e.name}</span>
            <span class="column-range">${e.range}</span>
          </div>
          <span class="column-count">${i.length}/${t.length}</span>
        </div>
        <div class="stack">
          ${Ce(
      n,
      (l) => l.id,
      (l) => this._renderQuest(l, !1, 0)
    )}
          ${Ce(
      i,
      (l) => l.id,
      (l, a) => this._renderQuest(l, !0, a)
    )}
          ${e.key === "afternoon" ? this._renderRollup() : g}
        </div>
      </section>
    `;
  }
  _renderQuest(e, t, n) {
    if (t) {
      const o = Me[n % Me.length], l = e.completed_at ? Ht(e.completed_at, this._timeZone()) : "";
      return p`
        <div class="quest sealed" data-instance-id=${e.id}>
          <span class="tile" aria-hidden="true">${Y}</span>
          <div class="body">
            <span class="quest-title">${e.title}</span>
            <span class="meta">
              ${l ? `Claimed ${l}` : "Claimed"}
            </span>
          </div>
          <span
            class="seal"
            aria-hidden="true"
            style="--seal-rot: ${o}deg"
          >
            ${R}
          </span>
        </div>
      `;
    }
    const i = jt(e.due_time), r = e.overdue ? {
      text: i ? `Overdue · due ${i}` : "Overdue",
      late: !0
    } : {
      text: i ? `Due by ${i}` : "Due today",
      late: !1
    };
    return p`
      <div
        class="quest tappable"
        role="button"
        tabindex="0"
        data-instance-id=${e.id}
        aria-label="Complete ${e.title}"
        @click=${() => this._openConfirm(e.id)}
        @keydown=${(o) => {
      (o.key === "Enter" || o.key === " ") && (o.preventDefault(), this._openConfirm(e.id));
    }}
      >
        <span class="tile" aria-hidden="true">${Y}</span>
        <div class="body">
          <span class="quest-title">${e.title}</span>
          <span class="meta ${r.late ? "late" : g}">${r.text}</span>
        </div>
        <button
          class="complete"
          type="button"
          @click=${() => this._openConfirm(e.id)}
        >
          ${R}
          <span>Complete</span>
        </button>
      </div>
    `;
  }
  _renderRollup() {
    const e = this._otherChildren();
    if (e.length === 0)
      return g;
    const t = e.slice(0, 2).map((n) => n.present ? n.due > 0 && n.completed >= n.due ? `${n.name} has finished their log.` : n.due > n.completed ? `${n.name} has ${n.due - n.completed} quests left.` : `${n.name} has no quests today.` : n.returnsWeekday ? `${n.name} is on travels until ${n.returnsWeekday}.` : `${n.name} is on travels.`);
    return p`
      <div class="rollup">
        <span class="rollup-label">Party roll-up</span>
        <p class="rollup-body">${t.join(" ")}</p>
      </div>
    `;
  }
  _renderConfirm() {
    if (this._confirm === null)
      return g;
    const e = this._instances().find(
      (n) => n.id === this._confirm
    );
    if (!e)
      return g;
    const t = Oe.find((n) => n.key === e.window);
    return p`
      <div class="scrim" @click=${() => this._closeConfirm()}>
        <div
          class="dialog"
          role="dialog"
          aria-modal="true"
          @click=${(n) => n.stopPropagation()}
        >
          <div class="dialog-header">
            <span class="dialog-tile" aria-hidden="true">${Y}</span>
            <div class="dialog-titles">
              <span class="dialog-kicker">
                ${t?.name ?? "Quest"}
              </span>
              <span class="dialog-quest-title">${e.title}</span>
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
              ${Wt}
              <span>Not yet</span>
            </button>
            <button
              class="confirm-button do-complete"
              type="button"
              @click=${() => this._confirmComplete()}
            >
              ${R}
              <span>Complete</span>
            </button>
          </div>
        </div>
      </div>
    `;
  }
  _openConfirm(e) {
    this._confirm = e, this._armConfirmTimer();
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
    const e = this._boardPath();
    e && (window.history.pushState(null, "", e), window.dispatchEvent(new Event("location-changed")));
  }
  _stopClock() {
    this._clockTimer !== void 0 && (window.clearInterval(this._clockTimer), this._clockTimer = void 0);
  }
  _onActivity = () => {
    this._armIdle(), this._confirm !== null && this._armConfirmTimer();
  };
}
customElements.define("nestquest-quest-log-card", nn);
oe({
  type: "nestquest-quest-log-card",
  name: "NestQuest Quest Log",
  description: "One child's daily quests, grouped by window."
});
const sn = ":host{--nq-brand-blue: #3B3AB8;--nq-brand-purple: #A035CC;--nq-brand-gradient: linear-gradient(135deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-brand-gradient-h: linear-gradient(90deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-a-page: #F4F4F6;--nq-a-surface: #FFFFFF;--nq-a-surface-subtle: #FAFAFA;--nq-a-selected: #EBEBF8;--nq-a-border: #E4E4EA;--nq-a-divider: #EDEDF1;--nq-a-ink: #18181D;--nq-a-ink-secondary: #52525E;--nq-a-ink-tertiary: #70707E;--nq-a-success: #15803D;--nq-a-danger: #DC2626;--nq-a-danger-strong: #B91C1C;--nq-a-danger-bg: #FEE2E2;--nq-a-warning-ink: #92400E;--nq-a-warning-ink-2: #78350F;--nq-a-warning-bg: #FEF3C7;--nq-a-warning-border: rgba(217,119,6,.35);--nq-a-info-bg: #DBEAFE;--nq-a-info-ink: #1E3A8A;--nq-a-info-icon: #1D4ED8;--nq-a-reversal: #7D28A0;--nq-a-font: Nunito, system-ui, sans-serif;--nq-a-size-screen: 24px;--nq-a-size-hero: 32px;--nq-a-size-card-title: 19px;--nq-a-size-stat: 22px;--nq-a-size-row: 13.5px;--nq-a-size-meta: 11px;--nq-a-size-label: 10px;--nq-a-track-label: .1em;--nq-a-density-page-pad: 14px 16px 92px;--nq-a-density-gap: 10px;--nq-a-density-card-pad: 13px;--nq-a-density-row-pad: 11px 13px;--nq-a-density-radius: 8px;--nq-a-density-shadow: none;--nq-a-tabbar-height: 70px;--nq-a-tap-min: 44px;--nq-a-radius-pill: 9999px;--nq-a-radius-sheet: 20px 20px 0 0;--nq-a-sheet-shadow: 0 -8px 28px rgba(9,9,11,.18);--nq-a-progress-height: 6px;--nq-ease-out: cubic-bezier(0, 0, .2, 1);--nq-dur-micro: .12s;--nq-dur-base: .2s;--nq-dur-modal: .35s}";
class rn extends C {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 }
  };
  static styles = [v(sn)];
  hass;
  _config;
  setConfig(e) {
    if (!e || typeof e != "object")
      throw new Error("Invalid configuration");
    this._config = e;
  }
  getCardSize() {
    return 8;
  }
  render() {
    return p`<div>NestQuest Admin</div>`;
  }
}
customElements.define("nestquest-admin-card", rn);
oe({
  type: "nestquest-admin-card",
  name: "NestQuest Admin",
  description: "Parent phone view for today, tasks, schedule, and history."
});
const on = "/nestquest-static/nestquest-fonts.css";
if (!document.querySelector('link[data-nq-fonts=""]')) {
  const s = document.createElement("link");
  s.rel = "stylesheet", s.href = on, s.dataset.nqFonts = "", document.head.appendChild(s);
}

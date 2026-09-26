const F = globalThis, se = F.ShadowRoot && (F.ShadyCSS === void 0 || F.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype, ie = /* @__PURE__ */ Symbol(), ce = /* @__PURE__ */ new WeakMap();
let Ie = class {
  constructor(e, t, n) {
    if (this._$cssResult$ = !0, n !== ie) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = e, this.t = t;
  }
  get styleSheet() {
    let e = this.o;
    const t = this.t;
    if (se && e === void 0) {
      const n = t !== void 0 && t.length === 1;
      n && (e = ce.get(t)), e === void 0 && ((this.o = e = new CSSStyleSheet()).replaceSync(this.cssText), n && ce.set(t, e));
    }
    return e;
  }
  toString() {
    return this.cssText;
  }
};
const v = (s) => new Ie(typeof s == "string" ? s : s + "", void 0, ie), He = (s, ...e) => {
  const t = s.length === 1 ? s[0] : e.reduce((n, i, a) => n + ((r) => {
    if (r._$cssResult$ === !0) return r.cssText;
    if (typeof r == "number") return r;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + r + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(i) + s[a + 1], s[0]);
  return new Ie(t, s, ie);
}, Ge = (s, e) => {
  if (se) s.adoptedStyleSheets = e.map((t) => t instanceof CSSStyleSheet ? t : t.styleSheet);
  else for (const t of e) {
    const n = document.createElement("style"), i = F.litNonce;
    i !== void 0 && n.setAttribute("nonce", i), n.textContent = t.cssText, s.appendChild(n);
  }
}, de = se ? (s) => s : (s) => s instanceof CSSStyleSheet ? ((e) => {
  let t = "";
  for (const n of e.cssRules) t += n.cssText;
  return v(t);
})(s) : s;
const { is: Ke, defineProperty: Je, getOwnPropertyDescriptor: Xe, getOwnPropertyNames: Ye, getOwnPropertySymbols: et, getPrototypeOf: tt } = Object, Z = globalThis, pe = Z.trustedTypes, nt = pe ? pe.emptyScript : "", st = Z.reactiveElementPolyfillSupport, P = (s, e) => s, ne = { toAttribute(s, e) {
  switch (e) {
    case Boolean:
      s = s ? nt : null;
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
} }, je = (s, e) => !Ke(s, e), he = { attribute: !0, type: String, converter: ne, reflect: !1, useDefault: !1, hasChanged: je };
Symbol.metadata ??= /* @__PURE__ */ Symbol("metadata"), Z.litPropertyMetadata ??= /* @__PURE__ */ new WeakMap();
let T = class extends HTMLElement {
  static addInitializer(e) {
    this._$Ei(), (this.l ??= []).push(e);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(e, t = he) {
    if (t.state && (t.attribute = !1), this._$Ei(), this.prototype.hasOwnProperty(e) && ((t = Object.create(t)).wrapped = !0), this.elementProperties.set(e, t), !t.noAccessor) {
      const n = /* @__PURE__ */ Symbol(), i = this.getPropertyDescriptor(e, n, t);
      i !== void 0 && Je(this.prototype, e, i);
    }
  }
  static getPropertyDescriptor(e, t, n) {
    const { get: i, set: a } = Xe(this.prototype, e) ?? { get() {
      return this[t];
    }, set(r) {
      this[t] = r;
    } };
    return { get: i, set(r) {
      const l = i?.call(this);
      a?.call(this, r), this.requestUpdate(e, l, n);
    }, configurable: !0, enumerable: !0 };
  }
  static getPropertyOptions(e) {
    return this.elementProperties.get(e) ?? he;
  }
  static _$Ei() {
    if (this.hasOwnProperty(P("elementProperties"))) return;
    const e = tt(this);
    e.finalize(), e.l !== void 0 && (this.l = [...e.l]), this.elementProperties = new Map(e.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(P("finalized"))) return;
    if (this.finalized = !0, this._$Ei(), this.hasOwnProperty(P("properties"))) {
      const t = this.properties, n = [...Ye(t), ...et(t)];
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
      for (const i of n) t.unshift(de(i));
    } else e !== void 0 && t.push(de(e));
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
    return Ge(e, this.constructor.elementStyles), e;
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
      const a = (n.converter?.toAttribute !== void 0 ? n.converter : ne).toAttribute(t, n.type);
      this._$Em = e, a == null ? this.removeAttribute(i) : this.setAttribute(i, a), this._$Em = null;
    }
  }
  _$AK(e, t) {
    const n = this.constructor, i = n._$Eh.get(e);
    if (i !== void 0 && this._$Em !== i) {
      const a = n.getPropertyOptions(i), r = typeof a.converter == "function" ? { fromAttribute: a.converter } : a.converter?.fromAttribute !== void 0 ? a.converter : ne;
      this._$Em = i;
      const l = r.fromAttribute(t, a.type);
      this[i] = l ?? this._$Ej?.get(i) ?? l, this._$Em = null;
    }
  }
  requestUpdate(e, t, n, i = !1, a) {
    if (e !== void 0) {
      const r = this.constructor;
      if (i === !1 && (a = this[e]), n ??= r.getPropertyOptions(e), !((n.hasChanged ?? je)(a, t) || n.useDefault && n.reflect && a === this._$Ej?.get(e) && !this.hasAttribute(r._$Eu(e, n)))) return;
      this.C(e, t, n);
    }
    this.isUpdatePending === !1 && (this._$ES = this._$EP());
  }
  C(e, t, { useDefault: n, reflect: i, wrapped: a }, r) {
    n && !(this._$Ej ??= /* @__PURE__ */ new Map()).has(e) && (this._$Ej.set(e, r ?? t ?? this[e]), a !== !0 || r !== void 0) || (this._$AL.has(e) || (this.hasUpdated || n || (t = void 0), this._$AL.set(e, t)), i === !0 && this._$Em !== e && (this._$Eq ??= /* @__PURE__ */ new Set()).add(e));
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
        for (const [i, a] of this._$Ep) this[i] = a;
        this._$Ep = void 0;
      }
      const n = this.constructor.elementProperties;
      if (n.size > 0) for (const [i, a] of n) {
        const { wrapped: r } = a, l = this[i];
        r !== !0 || this._$AL.has(i) || l === void 0 || this.C(i, void 0, a, l);
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
T.elementStyles = [], T.shadowRootOptions = { mode: "open" }, T[P("elementProperties")] = /* @__PURE__ */ new Map(), T[P("finalized")] = /* @__PURE__ */ new Map(), st?.({ ReactiveElement: T }), (Z.reactiveElementVersions ??= []).push("2.1.2");
const ae = globalThis, ue = (s) => s, Q = ae.trustedTypes, fe = Q ? Q.createPolicy("lit-html", { createHTML: (s) => s }) : void 0, Re = "$lit$", k = `lit$${Math.random().toFixed(9).slice(2)}$`, Ue = "?" + k, it = `<${Ue}>`, A = document, I = () => A.createComment(""), H = (s) => s === null || typeof s != "object" && typeof s != "function", re = Array.isArray, at = (s) => re(s) || typeof s?.[Symbol.iterator] == "function", K = `[ 	
\f\r]`, L = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g, me = /-->/g, ge = />/g, $ = RegExp(`>|${K}(?:([^\\s"'>=/]+)(${K}*=${K}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g"), _e = /'/g, ye = /"/g, De = /^(?:script|style|textarea|title)$/i, Fe = (s) => (e, ...t) => ({ _$litType$: s, strings: e, values: t }), d = Fe(1), be = Fe(2), S = /* @__PURE__ */ Symbol.for("lit-noChange"), g = /* @__PURE__ */ Symbol.for("lit-nothing"), ve = /* @__PURE__ */ new WeakMap(), C = A.createTreeWalker(A, 129);
function Qe(s, e) {
  if (!re(s) || !s.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return fe !== void 0 ? fe.createHTML(e) : e;
}
const rt = (s, e) => {
  const t = s.length - 1, n = [];
  let i, a = e === 2 ? "<svg>" : e === 3 ? "<math>" : "", r = L;
  for (let l = 0; l < t; l++) {
    const o = s[l];
    let p, u, c = -1, f = 0;
    for (; f < o.length && (r.lastIndex = f, u = r.exec(o), u !== null); ) f = r.lastIndex, r === L ? u[1] === "!--" ? r = me : u[1] !== void 0 ? r = ge : u[2] !== void 0 ? (De.test(u[2]) && (i = RegExp("</" + u[2], "g")), r = $) : u[3] !== void 0 && (r = $) : r === $ ? u[0] === ">" ? (r = i ?? L, c = -1) : u[1] === void 0 ? c = -2 : (c = r.lastIndex - u[2].length, p = u[1], r = u[3] === void 0 ? $ : u[3] === '"' ? ye : _e) : r === ye || r === _e ? r = $ : r === me || r === ge ? r = L : (r = $, i = void 0);
    const h = r === $ && s[l + 1].startsWith("/>") ? " " : "";
    a += r === L ? o + it : c >= 0 ? (n.push(p), o.slice(0, c) + Re + o.slice(c) + k + h) : o + k + (c === -2 ? l : h);
  }
  return [Qe(s, a + (s[t] || "<?>") + (e === 2 ? "</svg>" : e === 3 ? "</math>" : "")), n];
};
class j {
  constructor({ strings: e, _$litType$: t }, n) {
    let i;
    this.parts = [];
    let a = 0, r = 0;
    const l = e.length - 1, o = this.parts, [p, u] = rt(e, t);
    if (this.el = j.createElement(p, n), C.currentNode = this.el.content, t === 2 || t === 3) {
      const c = this.el.content.firstChild;
      c.replaceWith(...c.childNodes);
    }
    for (; (i = C.nextNode()) !== null && o.length < l; ) {
      if (i.nodeType === 1) {
        if (i.hasAttributes()) for (const c of i.getAttributeNames()) if (c.endsWith(Re)) {
          const f = u[r++], h = i.getAttribute(c).split(k), m = /([.?@])?(.*)/.exec(f);
          o.push({ type: 1, index: a, name: m[2], strings: h, ctor: m[1] === "." ? lt : m[1] === "?" ? ct : m[1] === "@" ? dt : W }), i.removeAttribute(c);
        } else c.startsWith(k) && (o.push({ type: 6, index: a }), i.removeAttribute(c));
        if (De.test(i.tagName)) {
          const c = i.textContent.split(k), f = c.length - 1;
          if (f > 0) {
            i.textContent = Q ? Q.emptyScript : "";
            for (let h = 0; h < f; h++) i.append(c[h], I()), C.nextNode(), o.push({ type: 2, index: ++a });
            i.append(c[f], I());
          }
        }
      } else if (i.nodeType === 8) if (i.data === Ue) o.push({ type: 2, index: a });
      else {
        let c = -1;
        for (; (c = i.data.indexOf(k, c + 1)) !== -1; ) o.push({ type: 7, index: a }), c += k.length - 1;
      }
      a++;
    }
  }
  static createElement(e, t) {
    const n = A.createElement("template");
    return n.innerHTML = e, n;
  }
}
function z(s, e, t = s, n) {
  if (e === S) return e;
  let i = n !== void 0 ? t._$Co?.[n] : t._$Cl;
  const a = H(e) ? void 0 : e._$litDirective$;
  return i?.constructor !== a && (i?._$AO?.(!1), a === void 0 ? i = void 0 : (i = new a(s), i._$AT(s, t, n)), n !== void 0 ? (t._$Co ??= [])[n] = i : t._$Cl = i), i !== void 0 && (e = z(s, i._$AS(s, e.values), i, n)), e;
}
class ot {
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
    const { el: { content: t }, parts: n } = this._$AD, i = (e?.creationScope ?? A).importNode(t, !0);
    C.currentNode = i;
    let a = C.nextNode(), r = 0, l = 0, o = n[0];
    for (; o !== void 0; ) {
      if (r === o.index) {
        let p;
        o.type === 2 ? p = new N(a, a.nextSibling, this, e) : o.type === 1 ? p = new o.ctor(a, o.name, o.strings, this, e) : o.type === 6 && (p = new pt(a, this, e)), this._$AV.push(p), o = n[++l];
      }
      r !== o?.index && (a = C.nextNode(), r++);
    }
    return C.currentNode = A, i;
  }
  p(e) {
    let t = 0;
    for (const n of this._$AV) n !== void 0 && (n.strings !== void 0 ? (n._$AI(e, n, t), t += n.strings.length - 2) : n._$AI(e[t])), t++;
  }
}
class N {
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
    e = z(this, e, t), H(e) ? e === g || e == null || e === "" ? (this._$AH !== g && this._$AR(), this._$AH = g) : e !== this._$AH && e !== S && this._(e) : e._$litType$ !== void 0 ? this.$(e) : e.nodeType !== void 0 ? this.T(e) : at(e) ? this.k(e) : this._(e);
  }
  O(e) {
    return this._$AA.parentNode.insertBefore(e, this._$AB);
  }
  T(e) {
    this._$AH !== e && (this._$AR(), this._$AH = this.O(e));
  }
  _(e) {
    this._$AH !== g && H(this._$AH) ? this._$AA.nextSibling.data = e : this.T(A.createTextNode(e)), this._$AH = e;
  }
  $(e) {
    const { values: t, _$litType$: n } = e, i = typeof n == "number" ? this._$AC(e) : (n.el === void 0 && (n.el = j.createElement(Qe(n.h, n.h[0]), this.options)), n);
    if (this._$AH?._$AD === i) this._$AH.p(t);
    else {
      const a = new ot(i, this), r = a.u(this.options);
      a.p(t), this.T(r), this._$AH = a;
    }
  }
  _$AC(e) {
    let t = ve.get(e.strings);
    return t === void 0 && ve.set(e.strings, t = new j(e)), t;
  }
  k(e) {
    re(this._$AH) || (this._$AH = [], this._$AR());
    const t = this._$AH;
    let n, i = 0;
    for (const a of e) i === t.length ? t.push(n = new N(this.O(I()), this.O(I()), this, this.options)) : n = t[i], n._$AI(a), i++;
    i < t.length && (this._$AR(n && n._$AB.nextSibling, i), t.length = i);
  }
  _$AR(e = this._$AA.nextSibling, t) {
    for (this._$AP?.(!1, !0, t); e !== this._$AB; ) {
      const n = ue(e).nextSibling;
      ue(e).remove(), e = n;
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
  constructor(e, t, n, i, a) {
    this.type = 1, this._$AH = g, this._$AN = void 0, this.element = e, this.name = t, this._$AM = i, this.options = a, n.length > 2 || n[0] !== "" || n[1] !== "" ? (this._$AH = Array(n.length - 1).fill(new String()), this.strings = n) : this._$AH = g;
  }
  _$AI(e, t = this, n, i) {
    const a = this.strings;
    let r = !1;
    if (a === void 0) e = z(this, e, t, 0), r = !H(e) || e !== this._$AH && e !== S, r && (this._$AH = e);
    else {
      const l = e;
      let o, p;
      for (e = a[0], o = 0; o < a.length - 1; o++) p = z(this, l[n + o], t, o), p === S && (p = this._$AH[o]), r ||= !H(p) || p !== this._$AH[o], p === g ? e = g : e !== g && (e += (p ?? "") + a[o + 1]), this._$AH[o] = p;
    }
    r && !i && this.j(e);
  }
  j(e) {
    e === g ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, e ?? "");
  }
}
class lt extends W {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(e) {
    this.element[this.name] = e === g ? void 0 : e;
  }
}
class ct extends W {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(e) {
    this.element.toggleAttribute(this.name, !!e && e !== g);
  }
}
class dt extends W {
  constructor(e, t, n, i, a) {
    super(e, t, n, i, a), this.type = 5;
  }
  _$AI(e, t = this) {
    if ((e = z(this, e, t, 0) ?? g) === S) return;
    const n = this._$AH, i = e === g && n !== g || e.capture !== n.capture || e.once !== n.once || e.passive !== n.passive, a = e !== g && (n === g || i);
    i && this.element.removeEventListener(this.name, this, n), a && this.element.addEventListener(this.name, this, e), this._$AH = e;
  }
  handleEvent(e) {
    typeof this._$AH == "function" ? this._$AH.call(this.options?.host ?? this.element, e) : this._$AH.handleEvent(e);
  }
}
class pt {
  constructor(e, t, n) {
    this.element = e, this.type = 6, this._$AN = void 0, this._$AM = t, this.options = n;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(e) {
    z(this, e);
  }
}
const ht = { I: N }, ut = ae.litHtmlPolyfillSupport;
ut?.(j, N), (ae.litHtmlVersions ??= []).push("3.3.3");
const ft = (s, e, t) => {
  const n = t?.renderBefore ?? e;
  let i = n._$litPart$;
  if (i === void 0) {
    const a = t?.renderBefore ?? null;
    n._$litPart$ = i = new N(e.insertBefore(I(), a), a, void 0, t ?? {});
  }
  return i._$AI(s), i;
};
const oe = globalThis;
let M = class extends T {
  constructor() {
    super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
  }
  createRenderRoot() {
    const e = super.createRenderRoot();
    return this.renderOptions.renderBefore ??= e.firstChild, e;
  }
  update(e) {
    const t = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(e), this._$Do = ft(t, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(!0);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(!1);
  }
  render() {
    return S;
  }
};
M._$litElement$ = !0, M.finalized = !0, oe.litElementHydrateSupport?.({ LitElement: M });
const mt = oe.litElementPolyfillSupport;
mt?.({ LitElement: M });
(oe.litElementVersions ??= []).push("4.2.2");
const Ve = ':host{--nq-p-parchment-top: #f0e4c7;--nq-p-parchment-bottom: #ddcca3;--nq-p-parchment: radial-gradient(ellipse at 25% 10%, rgba(255,255,255,.5), transparent 55%), radial-gradient(ellipse at 85% 90%, rgba(120,86,44,.28), transparent 60%), repeating-linear-gradient(93deg, rgba(150,115,70,.05) 0 2px, transparent 2px 6px), repeating-linear-gradient(2deg, rgba(150,115,70,.04) 0 3px, transparent 3px 7px), linear-gradient(var(--nq-p-parchment-top), var(--nq-p-parchment-bottom));--nq-p-vignette: inset 0 0 200px rgba(80,52,20,.35);--nq-p-card-open: linear-gradient(#fdf7e6, #f2e7c9);--nq-p-card-done: linear-gradient(#f0e8d3, #e6dcc2);--nq-p-card-panel: linear-gradient(#fcf6e6, #f1e6ca);--nq-p-card-border: rgba(120,88,48,.38);--nq-p-panel-border: rgba(92,62,26,.4);--nq-p-card-shadow: 0 3px 0 rgba(120,88,48,.2), inset 0 1px 0 rgba(255,255,255,.7);--nq-p-panel-shadow: 0 6px 0 rgba(92,62,26,.18), inset 0 2px 0 rgba(255,255,255,.7);--nq-p-frame-outer: 2px solid rgba(92,62,26,.45);--nq-p-frame-inner: 1px solid rgba(92,62,26,.28);--nq-p-rule: 2px solid rgba(92,62,26,.35);--nq-p-ink: #2b1f14;--nq-p-ink-secondary: #5c452a;--nq-p-ink-muted: #6f6455;--nq-p-ink-away: #4d4433;--nq-p-ink-late: #8f1526;--nq-brand-blue: #3B3AB8;--nq-brand-purple: #A035CC;--nq-brand-gradient: linear-gradient(135deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-p-icon-tile: var(--nq-brand-gradient);--nq-p-icon-tile-done: rgba(92,62,26,.16);--nq-p-crest: var(--nq-brand-gradient);--nq-p-crest-away: linear-gradient(135deg, #6b6b7a, #7a7286);--nq-p-seal: radial-gradient(circle at 35% 30%, #a8283a, #6d1322);--nq-p-seal-shadow: 0 4px 10px rgba(60,10,20,.4), inset 0 0 0 4px rgba(255,255,255,.14);--nq-p-seal-size: 78px;--nq-p-dock-bg: rgba(43,31,20,.9);--nq-p-dock-ink: #f7efdb;--nq-p-dock-ink-secondary: #d8c9a6;--nq-p-dock-divider: rgba(233,220,189,.3);--nq-p-dock-height: 84px;--nq-p-font-display: "Cinzel Decorative", Cinzel, serif;--nq-p-font-heading: Cinzel, serif;--nq-p-font-body: Nunito, system-ui, sans-serif;--nq-p-size-hero: 86px;--nq-p-size-wordmark: 66px;--nq-p-size-title: 56px;--nq-p-size-name: 48px;--nq-p-size-section: 32px;--nq-p-size-quest: 30px;--nq-p-size-body: 22px;--nq-p-size-label: 21px;--nq-p-track-label: .14em;--nq-p-track-kicker: .3em;--nq-p-quest-min-height: 116px;--nq-p-quest-gap: 24px;--nq-p-quest-pad: 22px;--nq-p-tile-size: 64px;--nq-p-button-height: 72px;--nq-p-button-min-width: 150px;--nq-p-confirm-button: 108px;--nq-p-radius-card: 12px;--nq-p-radius-panel: 20px;--nq-p-radius-pill: 9999px;--nq-p-page-inset: 62px;--nq-p-frame-inset: 26px;--nq-ease-out: cubic-bezier(0, 0, .2, 1);--nq-dur-micro: .12s;--nq-dur-base: .2s;--nq-dur-modal: .35s}';
function le(s) {
  window.customCards = window.customCards ?? [], window.customCards.push(s);
}
const gt = [
  "nestquest_quest_completed",
  "nestquest_quest_uncompleted",
  "nestquest_quest_missed",
  "nestquest_child_day_complete"
], xe = /* @__PURE__ */ new Map();
function V(s, e) {
  const t = `${s ?? "local"}|${JSON.stringify(e)}`, n = xe.get(t);
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
  return xe.set(t, i), i;
}
function _t(s) {
  const e = s?.config;
  if (!e || typeof e != "object")
    return;
  const t = e.time_zone;
  return typeof t == "string" && t.trim() ? t.trim() : void 0;
}
function J(s, e) {
  return `${V(e, { weekday: "long" }).format(s)}, ${V(e, { month: "short", day: "numeric" }).format(s)}`;
}
function yt(s, e) {
  return V(e, {
    hour: "numeric",
    minute: "2-digit",
    hour12: !0
  }).format(s);
}
const bt = {
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
}, vt = {
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
function we(s) {
  return typeof s == "string" ? s.trim() : "";
}
function X(s, e) {
  if (s == null || s === "")
    return e;
  const t = typeof s == "number" ? s : Number(s);
  return Number.isFinite(t) ? t : e;
}
function xt(s) {
  if (s === null || typeof s != "object" || Array.isArray(s))
    return "";
  const e = s.slug;
  return typeof e == "string" ? e.trim() : "";
}
function ke(s) {
  return Number.isFinite(s) ? Math.min(100, Math.max(0, s)) : 0;
}
function $e(s) {
  return Math.max(0, Math.round(s));
}
function wt(s) {
  return s.split(/[-_]+/).filter(Boolean).map((e) => e.charAt(0).toUpperCase() + e.slice(1)).join(" ");
}
function kt(s, e) {
  const t = V(e, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23"
  }).formatToParts(new Date(s)), n = (a) => {
    const r = t.find((l) => l.type === a);
    return r ? Number(r.value) : Number.NaN;
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
function $t(s, e) {
  if (typeof s != "string")
    return null;
  const t = s.split("-");
  if (t.length !== 3)
    return null;
  const [n, i, a] = t.map((o) => Number(o));
  if (!n || !i || !a)
    return null;
  if (!e) {
    const o = new Date(n, i - 1, a);
    return Number.isNaN(o.getTime()) ? null : o;
  }
  const r = Date.UTC(n, i - 1, a), l = new Date(r - kt(r, e));
  return Number.isNaN(l.getTime()) ? null : l;
}
function qt(s) {
  const e = bt[s];
  return e || s.charAt(0).toUpperCase() + s.slice(1);
}
function Ct(s, e) {
  return vt[s] ?? e;
}
const qe = "polygon(0 0, 100% 0, 100% 62%, 50% 100%, 0 62%)", Mt = "polygon(50% 0, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)", At = He`
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
    clip-path: ${v(Mt)};
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
    clip-path: ${v(qe)};
    background: rgba(255, 255, 255, 0.22);
  }

  .crest-face {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-bottom: 70px;
    clip-path: ${v(qe)};
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
`, St = d`<svg
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
</svg>`, Tt = d`<svg
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
</svg>`, zt = d`<svg
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
</svg>`, Et = d`<svg
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
</svg>`, Nt = d`<svg
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
</svg>`, Ce = {
  icon: Et,
  headline: "NestQuest is not set up yet",
  body: "A parent needs to finish setting up NestQuest before the party can gather."
}, Lt = {
  icon: Nt,
  headline: "The records cannot be reached",
  body: "The party's records are quiet right now. NestQuest will return shortly."
}, Bt = d`<svg
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
class Ot extends M {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 },
    _now: { state: !0 }
  };
  static styles = [v(Ve), At];
  hass;
  _config;
  _now = /* @__PURE__ */ new Date();
  _clockTimer;
  _unsubs = [];
  _subscribed = !1;
  _subGeneration = 0;
  _retryTimer;
  setConfig(e) {
    if (!e || typeof e != "object")
      throw new Error("Invalid configuration");
    this._config = e;
  }
  _hassConnection() {
    const e = this.hass?.connection;
    return !e || typeof e != "object" || typeof e.subscribeEvents != "function" ? null : e;
  }
  _subscribeLive() {
    if (!this.isConnected || this._subscribed)
      return;
    const e = this._hassConnection();
    if (!e)
      return;
    this._subscribed = !0;
    const t = ++this._subGeneration, n = (i) => {
      i.then((a) => {
        this._subscribed && t === this._subGeneration ? this._unsubs.push(a) : a();
      }).catch(() => {
        t === this._subGeneration && (this._unsubscribeLive(), this._armSubscribeRetry());
      });
    };
    for (const i of gt)
      n(
        e.subscribeEvents(() => this.requestUpdate(), i)
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
    for (const e of this._unsubs)
      e();
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
    const e = this._boardNotice();
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
        <p class="kicker">The Party · ${J(this._now, this._timeZone())}</p>
        ${e ? this._renderNotice(e) : d`
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
    return _t(this.hass);
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
    ).map((t) => t.trim()) : this._discoveredChildSlugs();
  }
  /** Zero-config discovery (Feature 20): the ordered child roster the
   *  integration publishes on the household rollup
   *  (custom_components/nestquest/sensor.py — ``child_roster``, the
   *  snapshot's sort_order, then id), each entry carrying the slug the
   *  per-child entity ids are built from.  Consulted only when the
   *  config has no child_order — explicit configuration wins. */
  _discoveredChildSlugs() {
    const t = this._state(
      "sensor.nestquest_household_quests_due_today"
    )?.attributes?.child_roster;
    return Array.isArray(t) ? t.map((n) => xt(n)).filter((n) => n.length > 0) : [];
  }
  _plates() {
    return this._childSlugs().map((e) => this._plate(e));
  }
  _plate(e) {
    const t = this._dueSensorResolution(e), n = this._state(`sensor.nestquest_${e}_quests_due_today`), i = this._state(
      `sensor.nestquest_${e}_quests_completed_today`
    ), a = this._state(
      `sensor.nestquest_${e}_completion_pct_today`
    ), r = this._state(
      `binary_sensor.nestquest_${e}_present_today`
    ), l = n?.attributes ?? {}, o = $e(X(n?.state, 0)), p = $e(X(i?.state, 0)), u = a ? X(a.state, Number.NaN) : Number.NaN, c = Number.isFinite(u) ? ke(u) : o > 0 ? ke(p / o * 100) : 0;
    let f = !0;
    const h = l.present;
    typeof h == "boolean" ? f = h : r && (f = String(r.state ?? "").trim().toLowerCase() === "on");
    let m = "";
    const _ = l.child_name;
    if (typeof _ == "string" && _.trim())
      m = _.trim();
    else {
      const G = r?.attributes?.child_name;
      typeof G == "string" && G.trim() && (m = G.trim());
    }
    m || (m = wt(e));
    const x = $t(
      r?.attributes?.next_present,
      this._timeZone()
    ), R = x ? `Returns ${J(x, this._timeZone())}` : null;
    return {
      slug: e,
      name: m,
      initial: (m.charAt(0) || "?").toUpperCase(),
      present: t === null ? f : !1,
      completed: p,
      due: o,
      pct: c,
      returns: R,
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
    return e.length === 0 ? Ce : e.every((t) => t.unresolved !== null) ? e.some((t) => t.unresolved === "stale") ? Lt : Ce : null;
  }
  _renderNotice(e) {
    return d`
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
    return e.unresolved ? d`
        <div class="plate unknown">
          <span class="crest away">
            <span class="crest-face">
              <span class="initial">${e.initial}</span>
            </span>
          </span>
          <span class="name">${e.name}</span>
          <span class="pill away">
            ${zt}
            <span>Unknown</span>
          </span>
          <span class="progress-line">&mdash;</span>
          <span class="bar"></span>
        </div>
      ` : e.present ? d`
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
            ${St}
            <span>Home today</span>
          </span>
          <span class="progress-line">
            ${e.completed} of ${e.due} quests claimed
          </span>
          <span class="bar">
            <span class="fill" style="width: ${e.pct}%"></span>
          </span>
        </button>
      ` : d`
      <div class="plate away">
        <span class="crest away">
          <span class="crest-face">
            <span class="initial">${e.initial}</span>
          </span>
        </span>
        <span class="name">${e.name}</span>
        <span class="pill away">
          ${Tt}
          <span>On travels</span>
        </span>
        <span class="progress-line">${e.returns ?? "Returns —"}</span>
        <span class="bar"></span>
      </div>
    `;
  }
  _openQuestLog(e) {
    const t = we(this._config?.quest_log_path);
    t && (window.history.pushState(null, "", `${t.replace(/\/+$/, "")}/${e}`), window.dispatchEvent(new Event("location-changed")));
  }
  _dockWeather() {
    const e = we(this._config?.weather_entity);
    if (!e)
      return null;
    const t = this._state(e);
    if (!t)
      return null;
    const n = String(t.state ?? "").trim();
    if (!n || n === "unavailable" || n === "unknown")
      return null;
    const i = t.attributes ?? {};
    let a = null, r = null;
    const l = i.forecast;
    if (Array.isArray(l) && l.length > 0) {
      const o = l[0];
      if (o && typeof o == "object") {
        const p = o;
        a = this._optionalNumber(p.temperature), r = this._optionalNumber(p.templow);
      }
    }
    return {
      condition: n,
      temperature: this._optionalNumber(i.temperature),
      high: a,
      low: r
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
      return d`
        <div class="dock">
          <span class="date">${J(this._now, this._timeZone())}</span>
          <span class="divider"></span>
          <span class="clock">${yt(this._now, this._timeZone())}</span>
        </div>
      `;
    const t = qt(e.condition), n = Ct(e.condition, t), i = e.temperature === null ? g : d`<span class="temp">${Math.round(e.temperature)}°</span>`, a = e.high === null || e.low === null ? null : `${Math.round(e.high)}° / ${Math.round(e.low)}°`;
    return d`
      <div class="dock">
        ${Bt}
        ${i}
        <span class="divider"></span>
        <span class="condition">
          ${a === null ? t : `${t} · ${a}`}
        </span>
        <span class="divider"></span>
        <span class="condition">${n}</span>
      </div>
    `;
  }
}
customElements.define("nestquest-party-board-card", Ot);
le({
  type: "nestquest-party-board-card",
  name: "NestQuest Party Board",
  description: "Kids' attract screen for present and away adventurers."
});
const Pt = { CHILD: 2 }, It = (s) => (...e) => ({ _$litDirective$: s, values: e });
let Ht = class {
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
const { I: jt } = ht, Me = (s) => s, Ae = () => document.createComment(""), B = (s, e, t) => {
  const n = s._$AA.parentNode, i = e === void 0 ? s._$AB : e._$AA;
  if (t === void 0) {
    const a = n.insertBefore(Ae(), i), r = n.insertBefore(Ae(), i);
    t = new jt(a, r, s, s.options);
  } else {
    const a = t._$AB.nextSibling, r = t._$AM, l = r !== s;
    if (l) {
      let o;
      t._$AQ?.(s), t._$AM = s, t._$AP !== void 0 && (o = s._$AU) !== r._$AU && t._$AP(o);
    }
    if (a !== i || l) {
      let o = t._$AA;
      for (; o !== a; ) {
        const p = Me(o).nextSibling;
        Me(n).insertBefore(o, i), o = p;
      }
    }
  }
  return t;
}, q = (s, e, t = s) => (s._$AI(e, t), s), Rt = {}, Ut = (s, e = Rt) => s._$AH = e, Dt = (s) => s._$AH, Y = (s) => {
  s._$AR(), s._$AA.remove();
};
const Se = (s, e, t) => {
  const n = /* @__PURE__ */ new Map();
  for (let i = e; i <= t; i++) n.set(s[i], i);
  return n;
}, Te = It(class extends Ht {
  constructor(s) {
    if (super(s), s.type !== Pt.CHILD) throw Error("repeat() can only be used in text expressions");
  }
  dt(s, e, t) {
    let n;
    t === void 0 ? t = e : e !== void 0 && (n = e);
    const i = [], a = [];
    let r = 0;
    for (const l of s) i[r] = n ? n(l, r) : r, a[r] = t(l, r), r++;
    return { values: a, keys: i };
  }
  render(s, e, t) {
    return this.dt(s, e, t).values;
  }
  update(s, [e, t, n]) {
    const i = Dt(s), { values: a, keys: r } = this.dt(e, t, n);
    if (!Array.isArray(i)) return this.ut = r, a;
    const l = this.ut ??= [], o = [];
    let p, u, c = 0, f = i.length - 1, h = 0, m = a.length - 1;
    for (; c <= f && h <= m; ) if (i[c] === null) c++;
    else if (i[f] === null) f--;
    else if (l[c] === r[h]) o[h] = q(i[c], a[h]), c++, h++;
    else if (l[f] === r[m]) o[m] = q(i[f], a[m]), f--, m--;
    else if (l[c] === r[m]) o[m] = q(i[c], a[m]), B(s, o[m + 1], i[c]), c++, m--;
    else if (l[f] === r[h]) o[h] = q(i[f], a[h]), B(s, i[c], i[f]), f--, h++;
    else if (p === void 0 && (p = Se(r, h, m), u = Se(l, c, f)), p.has(l[c])) if (p.has(l[f])) {
      const _ = u.get(r[h]), x = _ !== void 0 ? i[_] : null;
      if (x === null) {
        const R = B(s, i[c]);
        q(R, a[h]), o[h] = R;
      } else o[h] = q(x, a[h]), B(s, i[c], x), i[_] = null;
      h++;
    } else Y(i[f]), f--;
    else Y(i[c]), c++;
    for (; h <= m; ) {
      const _ = B(s, o[m + 1]);
      q(_, a[h]), o[h++] = _;
    }
    for (; c <= f; ) {
      const _ = i[c++];
      _ !== null && Y(_);
    }
    return this.ut = r, Ut(s, o), S;
  }
}), Ft = [
  {
    kind: "lucide",
    key: "lucide:bed",
    name: "bed",
    label: "Bed",
    viewBox: "0 0 24 24",
    paths: [
      "M2 4v16",
      "M2 8h18a2 2 0 0 1 2 2v10",
      "M2 17h20",
      "M6 8v9"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:bath",
    name: "bath",
    label: "Bath",
    viewBox: "0 0 24 24",
    paths: [
      "M10 4 8 6",
      "M17 19v2",
      "M2 12h20",
      "M7 19v2",
      "M9 5 7.621 3.621A2.121 2.121 0 0 0 4 5v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:shower-head",
    name: "shower-head",
    label: "Shower",
    viewBox: "0 0 24 24",
    paths: [
      "m4 4 2.5 2.5",
      "M13.5 6.5a4.95 4.95 0 0 0-7 7",
      "M15 5 5 15",
      "M14 17v.01",
      "M10 16v.01",
      "M13 13v.01",
      "M16 10v.01",
      "M11 20v.01",
      "M17 14v.01",
      "M20 11v.01"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:toilet",
    name: "toilet",
    label: "Toilet",
    viewBox: "0 0 24 24",
    paths: [
      "M7 12h13a1 1 0 0 1 1 1 5 5 0 0 1-5 5h-.598a.5.5 0 0 0-.424.765l1.544 2.47a.5.5 0 0 1-.424.765H5.402a.5.5 0 0 1-.424-.765L7 18",
      "M8 18a5 5 0 0 1-5-5V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:brush",
    name: "brush",
    label: "Brush",
    viewBox: "0 0 24 24",
    paths: [
      "m11 10 3 3",
      "M6.5 21A3.5 3.5 0 1 0 3 17.5a2.62 2.62 0 0 1-.708 1.792A1 1 0 0 0 3 21z",
      "M9.969 17.031 21.378 5.624a1 1 0 0 0-3.002-3.002L6.967 14.031"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:smile",
    name: "smile",
    label: "Smile",
    viewBox: "0 0 24 24",
    paths: [
      "M15 10V9",
      "M16.472 15a6 6 0 01-8.943 0",
      "M9 10V9",
      "M2 12a10 10 0 1 0 20 0a10 10 0 1 0 -20 0"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:shirt",
    name: "shirt",
    label: "Clothes",
    viewBox: "0 0 24 24",
    paths: [
      "M20.38 3.46 16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:washing-machine",
    name: "washing-machine",
    label: "Laundry",
    viewBox: "0 0 24 24",
    paths: [
      "M3 6h3",
      "M17 6h.01",
      "M5 2h14a2 2 0 0 1 2 2v16a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-16a2 2 0 0 1 2 -2z",
      "M7 13a5 5 0 1 0 10 0a5 5 0 1 0 -10 0",
      "M12 18a2.5 2.5 0 0 0 0-5 2.5 2.5 0 0 1 0-5"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:utensils",
    name: "utensils",
    label: "Meal",
    viewBox: "0 0 24 24",
    paths: [
      "M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2",
      "M7 2v20",
      "M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:cooking-pot",
    name: "cooking-pot",
    label: "Cooking",
    viewBox: "0 0 24 24",
    paths: [
      "M2 12h20",
      "M20 12v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8",
      "m4 8 16-4",
      "m8.86 6.78-.45-1.81a2 2 0 0 1 1.45-2.43l1.94-.48a2 2 0 0 1 2.43 1.46l.45 1.8"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:apple",
    name: "apple",
    label: "Snack",
    viewBox: "0 0 24 24",
    paths: [
      "M12 6.528V3a1 1 0 0 1 1-1h0",
      "M18.237 21A15 15 0 0 0 22 11a6 6 0 0 0-10-4.472A6 6 0 0 0 2 11a15.1 15.1 0 0 0 3.763 10 3 3 0 0 0 3.648.648 5.5 5.5 0 0 1 5.178 0A3 3 0 0 0 18.237 21"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:brush-cleaning",
    name: "brush-cleaning",
    label: "Sweep",
    viewBox: "0 0 24 24",
    paths: [
      "m16 22-1-4",
      "M19 14a1 1 0 0 0 1-1v-1a2 2 0 0 0-2-2h-3a1 1 0 0 1-1-1V4a2 2 0 0 0-4 0v5a1 1 0 0 1-1 1H6a2 2 0 0 0-2 2v1a1 1 0 0 0 1 1",
      "M19 14H5l-1.973 6.767A1 1 0 0 0 4 22h16a1 1 0 0 0 .973-1.233z",
      "m8 22 1-4"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:spray-can",
    name: "spray-can",
    label: "Clean",
    viewBox: "0 0 24 24",
    paths: [
      "M3 3h.01",
      "M7 5h.01",
      "M11 7h.01",
      "M3 7h.01",
      "M7 9h.01",
      "M3 11h.01",
      "M15 5h4v4h-4z",
      "m19 9 2 2v10c0 .6-.4 1-1 1h-6c-.6 0-1-.4-1-1V11l2-2",
      "m13 14 8-2",
      "m13 19 8-2"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:trash-2",
    name: "trash-2",
    label: "Bins",
    viewBox: "0 0 24 24",
    paths: [
      "M10 11v6",
      "M14 11v6",
      "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6",
      "M3 6h18",
      "M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:recycle",
    name: "recycle",
    label: "Recycling",
    viewBox: "0 0 24 24",
    paths: [
      "M7 19H4.815a1.83 1.83 0 0 1-1.57-.881 1.785 1.785 0 0 1-.004-1.784L7.196 9.5",
      "M11 19h8.203a1.83 1.83 0 0 0 1.556-.89 1.784 1.784 0 0 0 0-1.775l-1.226-2.12",
      "m14 16-3 3 3 3",
      "M8.293 13.596 7.196 9.5 3.1 10.598",
      "m9.344 5.811 1.093-1.892A1.83 1.83 0 0 1 11.985 3a1.784 1.784 0 0 1 1.546.888l3.943 6.843",
      "m13.378 9.633 4.096 1.098 1.097-4.096"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:sofa",
    name: "sofa",
    label: "Tidy",
    viewBox: "0 0 24 24",
    paths: [
      "M20 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v3",
      "M2 16a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5a2 2 0 0 0-4 0v1.5a.5.5 0 0 1-.5.5h-11a.5.5 0 0 1-.5-.5V11a2 2 0 0 0-4 0z",
      "M4 18v2",
      "M20 18v2",
      "M12 4v9"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:house",
    name: "house",
    label: "Home",
    viewBox: "0 0 24 24",
    paths: [
      "M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8",
      "M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:backpack",
    name: "backpack",
    label: "School bag",
    viewBox: "0 0 24 24",
    paths: [
      "M4 10a4 4 0 0 1 4-4h8a4 4 0 0 1 4 4v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z",
      "M8 10h8",
      "M8 18h8",
      "M8 22v-6a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v6",
      "M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:book-open",
    name: "book-open",
    label: "Reading",
    viewBox: "0 0 24 24",
    paths: [
      "M12 5v16",
      "M20.001 19A2 2 0 0022 17V5a2 2 0 00-1.999-2L16 3.002A5 5 0 0012 5a5 5 0 00-4-2H4a2 2 0 00-2 2v12a2 2 0 001.999 2H8a5 5 0 014 2 5 5 0 014-2z"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:pencil",
    name: "pencil",
    label: "Homework",
    viewBox: "0 0 24 24",
    paths: [
      "M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z",
      "m15 5 4 4"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:music",
    name: "music",
    label: "Music",
    viewBox: "0 0 24 24",
    paths: [
      "M9 18V5l12-2v13",
      "M3 18a3 3 0 1 0 6 0a3 3 0 1 0 -6 0",
      "M15 16a3 3 0 1 0 6 0a3 3 0 1 0 -6 0"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:dog",
    name: "dog",
    label: "Dog",
    viewBox: "0 0 24 24",
    paths: [
      "M11.25 16.25h1.5L12 17z",
      "M16 14v.5",
      "M4.42 11.247A13.152 13.152 0 0 0 4 14.556C4 18.728 7.582 21 12 21s8-2.272 8-6.444a11.702 11.702 0 0 0-.493-3.309",
      "M8 14v.5",
      "M8.5 8.5c-.384 1.05-1.083 2.028-2.344 2.5-1.931.722-3.576-.297-3.656-1-.113-.994 1.177-6.53 4-7 1.923-.321 3.651.845 3.651 2.235A7.497 7.497 0 0 1 14 5.277c0-1.39 1.844-2.598 3.767-2.277 2.823.47 4.113 6.006 4 7-.08.703-1.725 1.722-3.656 1-1.261-.472-1.855-1.45-2.239-2.5"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:cat",
    name: "cat",
    label: "Cat",
    viewBox: "0 0 24 24",
    paths: [
      "M12 5c.67 0 1.35.09 2 .26 1.78-2 5.03-2.84 6.42-2.26 1.4.58-.42 7-.42 7 .57 1.07 1 2.24 1 3.44C21 17.9 16.97 21 12 21s-9-3-9-7.56c0-1.25.5-2.4 1-3.44 0 0-1.89-6.42-.5-7 1.39-.58 4.72.23 6.5 2.23A9.04 9.04 0 0 1 12 5Z",
      "M8 14v.5",
      "M16 14v.5",
      "M11.25 16.25h1.5L12 17l-.75-.75Z"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:fish",
    name: "fish",
    label: "Fish",
    viewBox: "0 0 24 24",
    paths: [
      "M6.5 12c.94-3.46 4.94-6 8.5-6 3.56 0 6.06 2.54 7 6-.94 3.47-3.44 6-7 6s-7.56-2.53-8.5-6Z",
      "M18 12v.5",
      "M16 17.93a9.77 9.77 0 0 1 0-11.86",
      "M7 10.67C7 8 5.58 5.97 2.73 5.5c-1 1.5-1 5 .23 6.5-1.24 1.5-1.24 5-.23 6.5C5.58 18.03 7 16 7 13.33",
      "M10.46 7.26C10.2 5.88 9.17 4.24 8 3h5.8a2 2 0 0 1 1.98 1.67l.23 1.4",
      "m16.01 17.93-.23 1.4A2 2 0 0 1 13.8 21H9.5a5.96 5.96 0 0 0 1.49-3.98"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:sprout",
    name: "sprout",
    label: "Plants",
    viewBox: "0 0 24 24",
    paths: [
      "M14 9.536V7a4 4 0 0 1 4-4h1.5a.5.5 0 0 1 .5.5V5a4 4 0 0 1-4 4 4 4 0 0 0-4 4c0 2 1 3 1 5a5 5 0 0 1-1 3",
      "M4 9a5 5 0 0 1 8 4 5 5 0 0 1-8-4",
      "M5 21h14"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:droplets",
    name: "droplets",
    label: "Water",
    viewBox: "0 0 24 24",
    paths: [
      "M7 16.3c2.2 0 4-1.83 4-4.05 0-1.16-.57-2.26-1.71-3.19S7.29 6.75 7 5.3c-.29 1.45-1.14 2.84-2.29 3.76S3 11.1 3 12.25c0 2.22 1.8 4.05 4 4.05z",
      "M12.56 6.6A10.97 10.97 0 0 0 14 3.02c.5 2.5 2 4.9 4 6.5s3 3.5 3 5.5a6.98 6.98 0 0 1-11.91 4.97"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:bike",
    name: "bike",
    label: "Bike",
    viewBox: "0 0 24 24",
    paths: [
      "M15 17.5a3.5 3.5 0 1 0 7 0a3.5 3.5 0 1 0 -7 0",
      "M2 17.5a3.5 3.5 0 1 0 7 0a3.5 3.5 0 1 0 -7 0",
      "M14 5a1 1 0 1 0 2 0a1 1 0 1 0 -2 0",
      "M12 17.5V14l-3-3 4-3 2 3h2"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:volleyball",
    name: "volleyball",
    label: "Sport",
    viewBox: "0 0 24 24",
    paths: [
      "M11 7a16 16 20 0 1 10.98 4.362",
      "M12 12a13 13 0 0 1-8.66 5",
      "M16.83 13.634a16 16 0 0 1-9.267 7.328",
      "M20.66 17A13 13 0 0 0 12 12a13 13 0 0 1 0-10",
      "M8.17 15.366a16 16 0 0 1-1.713-11.69",
      "M2 12a10 10 0 1 0 20 0a10 10 0 1 0 -20 0"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:gamepad-2",
    name: "gamepad-2",
    label: "Games",
    viewBox: "0 0 24 24",
    paths: [
      "M6 11L10 11",
      "M8 9L8 13",
      "M15 12L15.01 12",
      "M18 10L18.01 10",
      "M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258-.007-.05-.011-.1-.017-.151A4 4 0 0 0 17.32 5z"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:star",
    name: "star",
    label: "Star",
    viewBox: "0 0 24 24",
    paths: [
      "M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:heart",
    name: "heart",
    label: "Heart",
    viewBox: "0 0 24 24",
    paths: [
      "M2 9.5a5.5 5.5 0 0 1 9.591-3.676.56.56 0 0 0 .818 0A5.49 5.49 0 0 1 22 9.5c0 2.29-1.5 4-3 5.5l-5.492 5.313a2 2 0 0 1-3 .019L5 15c-1.5-1.5-3-3.2-3-5.5"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:sun",
    name: "sun",
    label: "Morning",
    viewBox: "0 0 24 24",
    paths: [
      "M8 12a4 4 0 1 0 8 0a4 4 0 1 0 -8 0",
      "M12 2v2",
      "M12 20v2",
      "m4.93 4.93 1.41 1.41",
      "m17.66 17.66 1.41 1.41",
      "M2 12h2",
      "M20 12h2",
      "m6.34 17.66-1.41 1.41",
      "m19.07 4.93-1.41 1.41"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:moon",
    name: "moon",
    label: "Bedtime",
    viewBox: "0 0 24 24",
    paths: [
      "M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:clock",
    name: "clock",
    label: "Clock",
    viewBox: "0 0 24 24",
    paths: [
      "M2 12a10 10 0 1 0 20 0a10 10 0 1 0 -20 0",
      "M12 6v6l4 2"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:calendar",
    name: "calendar",
    label: "Calendar",
    viewBox: "0 0 24 24",
    paths: [
      "M8 2v3",
      "M16 2v3",
      "M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2z",
      "M3 9h18"
    ]
  },
  {
    kind: "lucide",
    key: "lucide:list-checks",
    name: "list-checks",
    label: "Checklist",
    viewBox: "0 0 24 24",
    paths: [
      "M13 5h8",
      "M13 12h8",
      "M13 19h8",
      "m3 17 2 2 4-4",
      "m3 7 2 2 4-4"
    ]
  }
], Qt = [
  {
    kind: "fa",
    key: "fa:broom",
    name: "broom",
    label: "Sweep",
    viewBox: "0 0 576 512",
    paths: [
      "M566.6 54.6c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0l-192 192-34.7-34.7c-4.2-4.2-10-6.6-16-6.6-12.5 0-22.6 10.1-22.6 22.6l0 29.1 108.3 108.3 29.1 0c12.5 0 22.6-10.1 22.6-22.6 0-6-2.4-11.8-6.6-16l-34.7-34.7 192-192zM341.1 353.4L222.6 234.9c-42.7-3.7-85.2 11.7-115.8 42.3l-8 8c-22.3 22.3-34.8 52.5-34.8 84 0 6.8 7.1 11.2 13.2 8.2l51.1-25.5c5-2.5 9.5 4.1 5.4 7.9L7.3 473.4C2.7 477.6 0 483.6 0 489.9 0 502.1 9.9 512 22.1 512l173.3 0c38.8 0 75.9-15.4 103.4-42.8 30.6-30.6 45.9-73.1 42.3-115.8z"
    ]
  },
  {
    kind: "fa",
    key: "fa:spray-can-sparkles",
    name: "spray-can-sparkles",
    label: "Clean",
    viewBox: "0 0 576 512",
    paths: [
      "M160 32l0 80 128 0 0-80c0-17.7-14.3-32-32-32L192 0c-17.7 0-32 14.3-32 32zm0 128c-53 0-96 43-96 96l0 208c0 26.5 21.5 48 48 48l224 0c26.5 0 48-21.5 48-48l0-208c0-53-43-96-96-96l-128 0zm64 96a80 80 0 1 1 0 160 80 80 0 1 1 0-160zM448 48c0-1.4-1-3-2.2-3.6L416 32 403.6 2.2C403 1 401.4 0 400 0s-3 1-3.6 2.2L384 32 354.2 44.4c-1.2 .6-2.2 2.2-2.2 3.6 0 1.4 1 3 2.2 3.6L384 64 396.4 93.8C397 95 398.6 96 400 96s3-1 3.6-2.2L416 64 445.8 51.6C447 51 448 49.4 448 48zm76.4 45.8C525 95 526.6 96 528 96s3-1 3.6-2.2L544 64 573.8 51.6c1.2-.6 2.2-2.2 2.2-3.6 0-1.4-1-3-2.2-3.6L544 32 531.6 2.2C531 1 529.4 0 528 0s-3 1-3.6 2.2L512 32 482.2 44.4c-1.2 .6-2.2 2.2-2.2 3.6 0 1.4 1 3 2.2 3.6L512 64 524.4 93.8zm7.2 100.4c-.6-1.2-2.2-2.2-3.6-2.2s-3 1-3.6 2.2L512 224 482.2 236.4c-1.2 .6-2.2 2.2-2.2 3.6 0 1.4 1 3 2.2 3.6L512 256 524.4 285.8c.6 1.2 2.2 2.2 3.6 2.2s3-1 3.6-2.2L544 256 573.8 243.6c1.2-.6 2.2-2.2 2.2-3.6 0-1.4-1-3-2.2-3.6L544 224 531.6 194.2zM512 144c0-1.4-1-3-2.2-3.6L480 128 467.6 98.2C467 97 465.4 96 464 96s-3 1-3.6 2.2L448 128 418.2 140.4c-1.2 .6-2.2 2.2-2.2 3.6 0 1.4 1 3 2.2 3.6L448 160 460.4 189.8c.6 1.2 2.2 2.2 3.6 2.2s3-1 3.6-2.2L480 160 509.8 147.6c1.2-.6 2.2-2.2 2.2-3.6z"
    ]
  },
  {
    kind: "fa",
    key: "fa:bucket",
    name: "bucket",
    label: "Mop",
    viewBox: "0 0 448 512",
    paths: [
      "M443.7 208c2.7 4.7 4.3 10.2 4.3 16 0 17.7-14.3 32-32 32l-5.1 0-22.4 213c-2.6 24.4-23.2 43-47.8 43l-233.6 0c-24.6 0-45.2-18.5-47.8-43L37.1 256 32 256c-17.7 0-32-14.3-32-32 0-5.8 1.6-11.3 4.3-16l439.4 0zM224-16c79.5 0 144 64.5 144 144l0 32-48 0 0-32c0-53-43-96-96-96s-96 43-96 96l0 32-48 0 0-32C80 48.5 144.5-16 224-16z"
    ]
  },
  {
    kind: "fa",
    key: "fa:soap",
    name: "soap",
    label: "Wash hands",
    viewBox: "0 0 512 512",
    paths: [
      "M208-32a48 48 0 1 1 0 96 48 48 0 1 1 0-96zM320 96a64 64 0 1 1 0 128 64 64 0 1 1 0-128zM352 0a32 32 0 1 1 64 0 32 32 0 1 1 -64 0zM96 160l112 0c0 23.8 7.4 45.9 20.1 64L160 224c-53 0-96 43-96 96s43 96 96 96l192 0c53 0 96-43 96-96 0-35.1-18.9-65.9-47-82.6 19-19.8 30.7-46.6 31-76.1 45.4 7.6 80 47.1 80 94.7l0 128c0 53-43 96-96 96L96 480c-53 0-96-43-96-96L0 256c0-53 43-96 96-96zm64 112l192 0c26.5 0 48 21.5 48 48s-21.5 48-48 48l-192 0c-26.5 0-48-21.5-48-48s21.5-48 48-48z"
    ]
  },
  {
    kind: "fa",
    key: "fa:sink",
    name: "sink",
    label: "Dishes",
    viewBox: "0 0 512 512",
    paths: [
      "M288 96c0-17.7 14.3-32 32-32s32 14.3 32 32 14.3 32 32 32 32-14.3 32-32c0-53-43-96-96-96s-96 43-96 96l0 192-64 0 0-40c0-30.9-25.1-56-56-56l-48 0c-13.3 0-24 10.7-24 24s10.7 24 24 24l48 0c4.4 0 8 3.6 8 8l0 40-80 0c-17.7 0-32 14.3-32 32s14.3 32 32 32l0 64c0 53 43 96 96 96l256 0c53 0 96-43 96-96l0-64c17.7 0 32-14.3 32-32s-14.3-32-32-32l-80 0 0-40c0-4.4 3.6-8 8-8l56 0c13.3 0 24-10.7 24-24s-10.7-24-24-24l-56 0c-30.9 0-56 25.1-56 56l0 40-64 0 0-192z"
    ]
  },
  {
    kind: "fa",
    key: "fa:jug-detergent",
    name: "jug-detergent",
    label: "Laundry",
    viewBox: "0 0 384 512",
    paths: [
      "M96 24c0-13.3 10.7-24 24-24l80 0c13.3 0 24 10.7 24 24l0 24 8 0c13.3 0 24 10.7 24 24s-10.7 24-24 24L88 96C74.7 96 64 85.3 64 72S74.7 48 88 48l8 0 0-24zM0 256c0-70.7 57.3-128 128-128l128 0c70.7 0 128 57.3 128 128l0 192c0 35.3-28.7 64-64 64L64 512c-35.3 0-64-28.7-64-64L0 256zm256 0l0 96c0 17.7 14.3 32 32 32s32-14.3 32-32l0-96c0-17.7-14.3-32-32-32s-32 14.3-32 32z"
    ]
  },
  {
    kind: "fa",
    key: "fa:socks",
    name: "socks",
    label: "Socks",
    viewBox: "0 0 512 512",
    paths: [
      "M252.8 0L176 0c-26.5 0-48 21.5-48 48l0 16 112 0 0-16c0-17.5 4.7-33.9 12.8-48zM128 112l0 128c0 20.1-9.5 39.1-25.6 51.2l-64 48c-24.2 18.1-38.4 46.6-38.4 76.8 0 53 43 96 96 96 15.4 0 30.5-3.7 44-10.7-17.6-23.9-28-53.4-28-85.3 0-45.3 21.3-88 57.6-115.2l64-48c4-3 6.4-7.8 6.4-12.8l0-128-112 0zm160 0l0 128c0 20.1-9.5 39.1-25.6 51.2l-64 48c-24.2 18.1-38.4 46.6-38.4 76.8 0 53 43 96 96 96 20.8 0 41-6.7 57.6-19.2l115.2-86.4C461 382.2 480 344.3 480 304l0-192-192 0zM480 64l0-16c0-26.5-21.5-48-48-48L336 0c-26.5 0-48 21.5-48 48l0 16 192 0z"
    ]
  },
  {
    kind: "fa",
    key: "fa:shirt",
    name: "shirt",
    label: "Clothes",
    viewBox: "0 0 640 512",
    paths: [
      "M320.2 112c44.2 0 80-35.8 80-80l53.5 0c17 0 33.3 6.7 45.3 18.7L617.6 169.4c12.5 12.5 12.5 32.8 0 45.3l-50.7 50.7c-12.5 12.5-32.8 12.5-45.3 0l-41.4-41.4 0 224c0 35.3-28.7 64-64 64l-192 0c-35.3 0-64-28.7-64-64l0-224-41.4 41.4c-12.5 12.5-32.8 12.5-45.3 0L22.9 214.6c-12.5-12.5-12.5-32.8 0-45.3L141.5 50.7c12-12 28.3-18.7 45.3-18.7l53.5 0c0 44.2 35.8 80 80 80z"
    ]
  },
  {
    kind: "fa",
    key: "fa:bed",
    name: "bed",
    label: "Bed",
    viewBox: "0 0 576 512",
    paths: [
      "M32 32c17.7 0 32 14.3 32 32l0 224 224 0 0-128c0-17.7 14.3-32 32-32l160 0c53 0 96 43 96 96l0 224c0 17.7-14.3 32-32 32s-32-14.3-32-32l0-64-448 0 0 64c0 17.7-14.3 32-32 32S0 465.7 0 448L0 64C0 46.3 14.3 32 32 32zm80 160a64 64 0 1 1 128 0 64 64 0 1 1 -128 0z"
    ]
  },
  {
    kind: "fa",
    key: "fa:couch",
    name: "couch",
    label: "Tidy",
    viewBox: "0 0 640 512",
    paths: [
      "M144 272C144 224.7 109.8 185.4 64.8 177.5 72 113.6 126.2 64 192 64l256 0c65.8 0 120 49.6 127.2 113.5-45 8-79.2 47.2-79.2 94.5l0 32-352 0 0-32zM0 384L0 272c0-26.5 21.5-48 48-48s48 21.5 48 48l0 80 448 0 0-80c0-26.5 21.5-48 48-48s48 21.5 48 48l0 112c0 35.3-28.7 64-64 64L64 448c-35.3 0-64-28.7-64-64z"
    ]
  },
  {
    kind: "fa",
    key: "fa:bath",
    name: "bath",
    label: "Bath",
    viewBox: "0 0 512 512",
    paths: [
      "M96 77.3c0-7.3 5.9-13.3 13.3-13.3 3.5 0 6.9 1.4 9.4 3.9l14.9 14.9c-3.6 9.1-5.5 18.9-5.5 29.2 0 19.9 7.2 38 19.2 52-5.3 9.2-4 21.1 3.8 29 9.4 9.4 24.6 9.4 33.9 0L289 89c9.4-9.4 9.4-24.6 0-33.9-7.8-7.9-19.8-9.1-29-3.8-14-12-32.1-19.2-52-19.2-10.3 0-20.2 2-29.2 5.5L163.9 22.6C149.4 8.1 129.7 0 109.3 0 66.6 0 32 34.6 32 77.3L32 256c-17.7 0-32 14.3-32 32s14.3 32 32 32l0 48c0 28.4 12.4 54 32 71.6L64 480c0 17.7 14.3 32 32 32s32-14.3 32-32l0-16 256 0 0 16c0 17.7 14.3 32 32 32s32-14.3 32-32l0-40.4c19.6-17.6 32-43.1 32-71.6l0-48c17.7 0 32-14.3 32-32s-14.3-32-32-32L96 256 96 77.3z"
    ]
  },
  {
    kind: "fa",
    key: "fa:tooth",
    name: "tooth",
    label: "Teeth",
    viewBox: "0 0 448 512",
    paths: [
      "M145 5.7L224 32 303 5.7C314.3 1.9 326 0 337.9 0 398.7 0 448 49.3 448 110.1l0 68.5c0 29.4-9.5 58.1-27.2 81.6l-1.1 1.5c-12.9 17.2-21.3 37.4-24.3 58.7L373.7 471.9c-3.3 23-23 40.1-46.2 40.1-22.8 0-42.3-16.5-46-39L261.3 351.6c-3-18.2-18.8-31.6-37.3-31.6s-34.2 13.4-37.3 31.6L166.5 473c-3.8 22.5-23.2 39-46 39-23.2 0-42.9-17.1-46.2-40.1L52.6 320.5c-3-21.3-11.4-41.5-24.3-58.7l-1.1-1.5C9.5 236.7 0 208.1 0 178.7l0-68.5C0 49.3 49.3 0 110.1 0 122 0 133.7 1.9 145 5.7z"
    ]
  },
  {
    kind: "fa",
    key: "fa:utensils",
    name: "utensils",
    label: "Meal",
    viewBox: "0 0 512 512",
    paths: [
      "M63.9 14.4C63.1 6.2 56.2 0 48 0s-15.1 6.2-16 14.3L17.9 149.7c-1.3 6-1.9 12.1-1.9 18.2 0 45.9 35.1 83.6 80 87.7L96 480c0 17.7 14.3 32 32 32s32-14.3 32-32l0-224.4c44.9-4.1 80-41.8 80-87.7 0-6.1-.6-12.2-1.9-18.2L223.9 14.3C223.1 6.2 216.2 0 208 0s-15.1 6.2-15.9 14.4L178.5 149.9c-.6 5.7-5.4 10.1-11.1 10.1-5.8 0-10.6-4.4-11.2-10.2L143.9 14.6C143.2 6.3 136.3 0 128 0s-15.2 6.3-15.9 14.6L99.8 149.8c-.5 5.8-5.4 10.2-11.2 10.2-5.8 0-10.6-4.4-11.1-10.1L63.9 14.4zM448 0C432 0 320 32 320 176l0 112c0 35.3 28.7 64 64 64l32 0 0 128c0 17.7 14.3 32 32 32s32-14.3 32-32l0-448c0-17.7-14.3-32-32-32z"
    ]
  },
  {
    kind: "fa",
    key: "fa:bowl-food",
    name: "bowl-food",
    label: "Set the table",
    viewBox: "0 0 512 512",
    paths: [
      "M0 176c0-35.3 28.7-64 64-64 .5 0 1.1 0 1.6 0 7.4-36.5 39.7-64 78.4-64 15 0 29 4.1 40.9 11.2 13.3-25.7 40.1-43.2 71.1-43.2s57.8 17.6 71.1 43.2c12-7.1 26-11.2 40.9-11.2 38.7 0 71 27.5 78.4 64 .5 0 1.1 0 1.6 0 35.3 0 64 28.7 64 64 0 11.7-3.1 22.6-8.6 32L8.6 208C3.1 198.6 0 187.7 0 176zM0 283.4C0 268.3 12.3 256 27.4 256l457.1 0c15.1 0 27.4 12.3 27.4 27.4 0 70.5-44.4 130.7-106.7 154.1L403.5 452c-2 16-15.6 28-31.8 28l-231.5 0c-16.1 0-29.8-12-31.8-28l-1.8-14.4C44.4 414.1 0 353.9 0 283.4z"
    ]
  },
  {
    kind: "fa",
    key: "fa:basket-shopping",
    name: "basket-shopping",
    label: "Groceries",
    viewBox: "0 0 576 512",
    paths: [
      "M288 0c6.6 0 12.9 2.7 17.4 7.5l144 152 .5 .5 78.1 0c17.7 0 32 14.3 32 32 0 14.5-9.6 26.7-22.8 30.7L491.1 429.9c-6.5 29.3-32.5 50.1-62.5 50.1l-281.3 0c-30 0-56-20.8-62.5-50.1l-46-207.2c-13.2-3.9-22.8-16.2-22.8-30.7 0-17.7 14.3-32 32-32l78.1 0 .5-.5 144-152C275.1 2.7 281.4 0 288 0zm0 58.9L192.2 160 383.8 160 288 58.9zM208 264c0-13.3-10.7-24-24-24s-24 10.7-24 24l0 112c0 13.3 10.7 24 24 24s24-10.7 24-24l0-112zm80-24c-13.3 0-24 10.7-24 24l0 112c0 13.3 10.7 24 24 24s24-10.7 24-24l0-112c0-13.3-10.7-24-24-24zm128 24c0-13.3-10.7-24-24-24s-24 10.7-24 24l0 112c0 13.3 10.7 24 24 24s24-10.7 24-24l0-112z"
    ]
  },
  {
    kind: "fa",
    key: "fa:trash-can",
    name: "trash-can",
    label: "Bins",
    viewBox: "0 0 448 512",
    paths: [
      "M136.7 5.9C141.1-7.2 153.3-16 167.1-16l113.9 0c13.8 0 26 8.8 30.4 21.9L320 32 416 32c17.7 0 32 14.3 32 32s-14.3 32-32 32L32 96C14.3 96 0 81.7 0 64S14.3 32 32 32l96 0 8.7-26.1zM32 144l384 0 0 304c0 35.3-28.7 64-64 64L96 512c-35.3 0-64-28.7-64-64l0-304zm88 64c-13.3 0-24 10.7-24 24l0 192c0 13.3 10.7 24 24 24s24-10.7 24-24l0-192c0-13.3-10.7-24-24-24zm104 0c-13.3 0-24 10.7-24 24l0 192c0 13.3 10.7 24 24 24s24-10.7 24-24l0-192c0-13.3-10.7-24-24-24zm104 0c-13.3 0-24 10.7-24 24l0 192c0 13.3 10.7 24 24 24s24-10.7 24-24l0-192c0-13.3-10.7-24-24-24z"
    ]
  },
  {
    kind: "fa",
    key: "fa:recycle",
    name: "recycle",
    label: "Recycling",
    viewBox: "0 0 512 512",
    paths: [
      "M152.3 60C198.5-20 314-20 360.2 60l37.3 64.6 27.7-16c8.4-4.9 18.9-4.2 26.6 1.7s11.1 15.9 8.6 25.3L436.9 223c-3.4 12.8-16.6 20.4-29.4 17l-87.4-23.4c-9.4-2.5-16.3-10.4-17.6-20s3.4-19.1 11.8-23.9l27.7-16-37.3-64.6c-21.6-37.3-75.4-37.3-97 0l-5.3 9.1c-8.8 15.3-28.4 20.5-43.7 11.7S138.2 84.5 147 69.1l5.3-9.1zM449.7 279.1c15.3-8.8 34.9-3.6 43.7 11.7l5.3 9.1c46.2 80-11.5 180-103.9 180l-74.6 0 0 32c0 9.7-5.8 18.5-14.8 22.2s-19.3 1.7-26.2-5.2l-64-64c-9.4-9.4-9.4-24.6 0-33.9l64-64c6.9-6.9 17.2-8.9 26.2-5.2s14.8 12.5 14.8 22.2l0 32 74.6 0c43.1 0 70.1-46.7 48.5-84l-5.3-9.1c-8.8-15.3-3.6-34.9 11.7-43.7zM51 235.4l-27.7-16c-8.4-4.9-13.1-14.3-11.8-23.9s8.2-17.5 17.6-20L116.5 152c12.8-3.4 26 4.2 29.4 17l23.4 87.4c2.5 9.4-.9 19.3-8.6 25.3s-18.2 6.6-26.6 1.7l-27.7-16-37.3 64.6c-21.6 37.3 5.4 84 48.5 84l10.6 0c17.7 0 32 14.3 32 32s-14.3 32-32 32l-10.6 0C25.3 480-32.4 380 13.8 300L51 235.4z"
    ]
  },
  {
    kind: "fa",
    key: "fa:dog",
    name: "dog",
    label: "Dog",
    viewBox: "0 0 576 512",
    paths: [
      "M32 112c16.6 0 30.2 12.6 31.8 28.7l.3 6.6C65.8 163.4 79.4 176 96 176l179.1 0 140.9 60.4 0 243.6c0 17.7-14.3 32-32 32l-32 0c-17.7 0-32-14.3-32-32l0-131.3C296 361 268.8 368 240 368s-56-7-80-19.3L160 480c0 17.7-14.3 32-32 32l-32 0c-17.7 0-32-14.3-32-32l0-245.6c-37.3-13.2-64-48.6-64-90.4 0-17.7 14.3-32 32-32zM355.8-32c7.7 0 14.9 3.6 19.6 9.8L392 0 444.1 0c12.7 0 24.9 5.1 33.9 14.1L496 32 552 32c13.3 0 24 10.7 24 24l0 24c0 44.2-35.8 80-80 80l-64 0-7 28-124.7-53.4 31.6-147.2C334.3-23.9 344.2-32 355.8-32zM448 44a20 20 0 1 0 0 40 20 20 0 1 0 0-40z"
    ]
  },
  {
    kind: "fa",
    key: "fa:cat",
    name: "cat",
    label: "Cat",
    viewBox: "0 0 576 512",
    paths: [
      "M64 96c53 0 96 43 96 96l0 85.8c29.7-44.7 77.8-76.2 133.4-84 25.6 60 85.2 102.1 154.6 102.1 10.9 0 21.6-1.1 32-3.1L480 480c0 17.7-14.3 32-32 32s-32-14.3-32-32l0-140.8-136 108.8 56 0c17.7 0 32 14.3 32 32s-14.3 32-32 32l-144 0c-53 0-96-43-96-96l0-224c0-16.6-12.6-30.2-28.7-31.8l-6.6-.3C44.6 158.2 32 144.6 32 128 32 110.3 46.3 96 64 96zM533.8 3.2C544.2-5.5 560 1.9 560 15.5L560 128c0 61.9-50.1 112-112 112S336 189.9 336 128l0-112.5c0-13.6 15.8-21 26.2-12.3L416 48 480 48 533.8 3.2zM400 108a20 20 0 1 0 0 40 20 20 0 1 0 0-40zm96 0a20 20 0 1 0 0 40 20 20 0 1 0 0-40z"
    ]
  },
  {
    kind: "fa",
    key: "fa:paw",
    name: "paw",
    label: "Pets",
    viewBox: "0 0 512 512",
    paths: [
      "M234.5 92.9c14.3 42.9-.3 86.2-32.6 96.8s-70.1-15.6-84.4-58.5 .3-86.2 32.6-96.8 70.1 15.6 84.4 58.5zM100.4 198.6c18.9 32.4 14.3 70.1-10.2 84.1s-59.7-.9-78.5-33.3-14.3-70.1 10.2-84.1 59.7 .9 78.5 33.3zM69.2 401.2C121.6 259.9 214.7 224 256 224s134.4 35.9 186.8 177.2c3.6 9.7 5.2 20.1 5.2 30.5l0 1.6c0 25.8-20.9 46.7-46.7 46.7-11.5 0-22.9-1.4-34-4.2l-88-22c-15.3-3.8-31.3-3.8-46.6 0l-88 22c-11.1 2.8-22.5 4.2-34 4.2-25.8 0-46.7-20.9-46.7-46.7l0-1.6c0-10.4 1.6-20.8 5.2-30.5zM421.8 282.7c-24.5-14-29.1-51.7-10.2-84.1s54-47.3 78.5-33.3 29.1 51.7 10.2 84.1-54 47.3-78.5 33.3zM310.1 189.7c-32.3-10.6-46.9-53.9-32.6-96.8s52.1-69.1 84.4-58.5 46.9 53.9 32.6 96.8-52.1 69.1-84.4 58.5z"
    ]
  },
  {
    kind: "fa",
    key: "fa:seedling",
    name: "seedling",
    label: "Plants",
    viewBox: "0 0 512 512",
    paths: [
      "M512 32C512 140.1 435.4 230.3 333.6 251.4 325.7 193.3 299.6 141 261.1 100.5 301.2 40 369.9 0 448 0l32 0c17.7 0 32 14.3 32 32zM0 96C0 78.3 14.3 64 32 64l32 0c123.7 0 224 100.3 224 224l0 192c0 17.7-14.3 32-32 32s-32-14.3-32-32l0-160C100.3 320 0 219.7 0 96z"
    ]
  },
  {
    kind: "fa",
    key: "fa:book",
    name: "book",
    label: "Reading",
    viewBox: "0 0 448 512",
    paths: [
      "M384 512L96 512c-53 0-96-43-96-96L0 96C0 43 43 0 96 0L400 0c26.5 0 48 21.5 48 48l0 288c0 20.9-13.4 38.7-32 45.3l0 66.7c17.7 0 32 14.3 32 32s-14.3 32-32 32l-32 0zM96 384c-17.7 0-32 14.3-32 32s14.3 32 32 32l256 0 0-64-256 0zm32-232c0 13.3 10.7 24 24 24l176 0c13.3 0 24-10.7 24-24s-10.7-24-24-24l-176 0c-13.3 0-24 10.7-24 24zm24 72c-13.3 0-24 10.7-24 24s10.7 24 24 24l176 0c13.3 0 24-10.7 24-24s-10.7-24-24-24l-176 0z"
    ]
  }
], O = { kind: "fallback", key: null }, Vt = 8, ze = new Map(Ft.map((s) => [s.name, s])), Zt = new Map(Qt.map((s) => [s.name, s]));
function Wt(s) {
  const e = [...s];
  return e.length === 0 || e.length > Vt ? !1 : !e.some((t) => new RegExp("[\\s<>&]|\\p{Cc}", "u").test(t));
}
function Gt(s) {
  if (!s || !s.trim()) return O;
  const e = s.indexOf(":");
  if (e === -1) return ze.get(s) ?? O;
  const t = s.slice(0, e), n = s.slice(e + 1);
  return t === "lucide" ? ze.get(n) ?? O : t === "fa" ? Zt.get(n) ?? O : t === "emoji" && Wt(n) ? { kind: "emoji", key: s, text: n } : O;
}
function Ee(s, e) {
  const t = Gt(s);
  switch (t.kind) {
    case "lucide":
      return d`<svg
        viewBox=${t.viewBox}
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
        data-icon=${t.key}
      >
        ${t.paths.map((n) => be`<path d=${n}></path>`)}
      </svg>`;
    case "fa":
      return d`<svg
        viewBox=${t.viewBox}
        fill="currentColor"
        aria-hidden="true"
        data-icon=${t.key}
      >
        ${t.paths.map((n) => be`<path d=${n}></path>`)}
      </svg>`;
    case "emoji":
      return d`<span class="emoji" data-icon=${t.key}>${t.text}</span>`;
    case "fallback":
      return e;
  }
}
const Kt = [
  "nestquest_quest_completed",
  "nestquest_quest_uncompleted",
  "nestquest_quest_missed",
  "nestquest_child_day_complete"
], Ne = /* @__PURE__ */ new Map();
function E(s, e) {
  const t = `${s ?? "local"}|${JSON.stringify(e)}`, n = Ne.get(t);
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
  return Ne.set(t, i), i;
}
function Jt(s) {
  const e = s?.config;
  if (!e || typeof e != "object")
    return;
  const t = e.time_zone;
  return typeof t == "string" && t.trim() ? t.trim() : void 0;
}
function U(s, e) {
  return `${E(e, { weekday: "long" }).format(s)}, ${E(e, { month: "short", day: "numeric" }).format(s)}`;
}
function Xt(s, e) {
  return E(e, { weekday: "long" }).format(s);
}
function Yt(s, e) {
  const t = new Date(s);
  return Number.isNaN(t.getTime()) ? "" : E(e, {
    hour: "numeric",
    minute: "2-digit",
    hour12: !0
  }).format(t);
}
function en(s, e) {
  return E(e, {
    hour: "numeric",
    minute: "2-digit",
    hour12: !0
  }).format(s);
}
function tn(s) {
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
function w(s) {
  return typeof s == "string" ? s.trim() : "";
}
function y(s, e) {
  if (s == null || s === "")
    return e;
  const t = typeof s == "number" ? s : Number(s);
  return Number.isFinite(t) ? t : e;
}
function b(s) {
  return Math.max(0, Math.round(s));
}
function ee(s) {
  return s.split(/[-_]+/).filter(Boolean).map((e) => e.charAt(0).toUpperCase() + e.slice(1)).join(" ");
}
function nn(s, e) {
  const t = E(e, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23"
  }).formatToParts(new Date(s)), n = (a) => {
    const r = t.find((l) => l.type === a);
    return r ? Number(r.value) : Number.NaN;
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
function Le(s, e) {
  if (typeof s != "string")
    return null;
  const t = s.split("-");
  if (t.length !== 3)
    return null;
  const [n, i, a] = t.map((o) => Number(o));
  if (!n || !i || !a)
    return null;
  if (!e) {
    const o = new Date(n, i - 1, a);
    return Number.isNaN(o.getTime()) ? null : o;
  }
  const r = Date.UTC(n, i - 1, a), l = new Date(r - nn(r, e));
  return Number.isNaN(l.getTime()) ? null : l;
}
function sn() {
  const s = window.location.pathname.split("/").filter(Boolean);
  return s.length > 0 ? s[s.length - 1].toLowerCase() : "";
}
function an(s) {
  if (!s || typeof s != "object")
    return null;
  const e = s, t = w(e.state).toLowerCase();
  if (t !== "open" && t !== "completed")
    return null;
  const n = y(e.id, 0);
  if (!n)
    return null;
  const i = y(e.child_id, 0);
  return {
    id: n,
    child_id: i > 0 ? i : null,
    title: w(e.title) || "Quest",
    icon: w(e.icon) || null,
    window: w(e.window).toLowerCase(),
    due_time: w(e.due_time) || null,
    state: t,
    overdue: e.overdue === !0,
    completed_at: w(e.completed_at) || null,
    on_time: e.on_time === !0 ? !0 : e.on_time === !1 ? !1 : null
  };
}
const rn = {
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
}, on = {
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
function ln(s) {
  const e = rn[s];
  return e || s.charAt(0).toUpperCase() + s.slice(1);
}
function cn(s, e) {
  return on[s] ?? e;
}
const Be = "polygon(0 0, 100% 0, 100% 62%, 50% 100%, 0 62%)", dn = "polygon(50% 0, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%)", Oe = [-9, 6, -4], pn = He`
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
    clip-path: ${v(Be)};
    background: rgba(255, 255, 255, 0.22);
  }

  .crest-face {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-bottom: 32px;
    clip-path: ${v(Be)};
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
    clip-path: ${v(dn)};
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

  .tile .emoji {
    font-size: 30px;
    line-height: 1;
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
`, D = d`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M20 6 9 17l-5-5"></path>
</svg>`, hn = d`<svg
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
</svg>`, te = d`<svg
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
</svg>`, un = d`<svg
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
</svg>`, Ze = d`<svg
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
</svg>`, fn = d`<svg
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path>
</svg>`, mn = d`<svg
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
</svg>`, gn = d`<svg
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
</svg>`, _n = d`<svg
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
</svg>`, yn = d`<svg
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
</svg>`, bn = d`<svg
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
</svg>`, vn = {
  icon: gn,
  headline: "No adventurer chosen",
  body: "Open The Party and tap your crest to open your quest log."
}, xn = {
  icon: _n,
  headline: "NestQuest is not set up yet",
  body: "A parent needs to finish setting up NestQuest."
}, wn = {
  icon: yn,
  headline: "The records cannot be reached",
  body: "The party's records are quiet right now. NestQuest will return shortly."
}, Pe = [
  { key: "morning", name: "Morning", range: "Until 11:59 AM", icon: un },
  { key: "afternoon", name: "Afternoon", range: "12:00–5:00 PM", icon: Ze },
  { key: "evening", name: "Evening", range: "5:00–9:00 PM", icon: fn }
];
class kn extends M {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 },
    _now: { state: !0 },
    _confirm: { state: !0 },
    _optimistic: { state: !0 },
    _toast: { state: !0 },
    _countdown: { state: !0 }
  };
  static styles = [v(Ve), pn];
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
  setConfig(e) {
    if (!e || typeof e != "object")
      throw new Error("Invalid configuration");
    this._config = e;
  }
  _hassConnection() {
    const e = this.hass?.connection;
    return !e || typeof e != "object" || typeof e.subscribeEvents != "function" ? null : e;
  }
  _subscribeLive() {
    if (!this.isConnected || this._subscribed)
      return;
    const e = this._hassConnection();
    if (!e)
      return;
    this._subscribed = !0;
    const t = ++this._subGeneration, n = (i) => {
      i.then((a) => {
        this._subscribed && t === this._subGeneration ? this._unsubs.push(a) : a();
      }).catch(() => {
        t === this._subGeneration && (this._unsubscribeLive(), this._armSubscribeRetry());
      });
    };
    for (const i of Kt)
      n(
        e.subscribeEvents(() => this.requestUpdate(), i)
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
    for (const e of this._unsubs)
      e();
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
    const e = this._logView();
    return d`
      <div class="board">
        <div class="frame frame-outer"></div>
        <div class="frame frame-inner"></div>
        ${this._renderMain(e)}
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
  _renderMain(e) {
    switch (e.kind) {
      case "no-adventurer":
        return this._renderNotice(vn);
      case "not-set-up":
        return this._renderNotice(xn);
      case "unreachable":
        return this._renderNotice(wn);
      case "away": {
        const t = ["The quest log unlocks when they return."];
        return e.returns && t.push(`Returns ${e.returns}`), d`
          ${this._renderHeader(e)}
          <div class="notice-wrap">
            <div class="notice away" role="status">
              ${mn}
              <span class="notice-headline">${e.name} is on travels</span>
              ${t.map((n) => d`<p class="notice-body">${n}</p>`)}
            </div>
          </div>
        `;
      }
      case "empty-day":
        return d`
          ${this._renderHeader(e)}
          <div class="notice-wrap">
            <div class="notice" role="status">
              ${Ze}
              <span class="notice-headline">No quests today</span>
              <p class="notice-body">
                ${`Nothing was posted for today, ${e.name}. Enjoy the day's rest!`}
              </p>
            </div>
          </div>
        `;
      case "complete-day": {
        const t = this._completeStats(), n = this._countdown ?? this._completeSeconds();
        return d`
          <div class="complete-screen" role="status">
            <span class="complete-seal" aria-hidden="true">${D}</span>
            <h1 class="complete-title">Quest complete</h1>
            <p class="complete-sub">${this._completeSub(e.name)}</p>
            <p class="complete-countdown">
              Returning to The Party in ${n} seconds
            </p>
            <div class="complete-stats">
              <div class="complete-stat">
                <span class="numeral">${t.claimed}</span>
                <span class="label">Quests claimed</span>
              </div>
              <div class="complete-stat">
                <span class="numeral">${t.onTime}</span>
                <span class="label">On time</span>
              </div>
              <div class="complete-stat">
                <span class="numeral">${t.late}</span>
                <span class="label">Late</span>
              </div>
              <div class="complete-stat">
                <span class="numeral">${t.party}</span>
                <span class="label">The Party</span>
              </div>
            </div>
          </div>
          ${this._renderDock()}
        `;
      }
      default:
        return d`
          ${this._renderHeader(e)}
          <div class="columns">
            ${Pe.map((t) => this._renderColumn(t))}
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
    const n = this._childName(e) ?? ee(e);
    if (!this._childPresent(e))
      return { kind: "away", name: n, returns: this._awayReturns(e) };
    const i = this._state(`binary_sensor.nestquest_${e}_all_done`);
    if (i && String(i.state ?? "").trim().toLowerCase() === "on")
      return { kind: "complete-day", name: n };
    const a = this._state(`sensor.nestquest_${e}_quests_due_today`);
    return b(y(a?.state, 0)) === 0 ? { kind: "empty-day", name: n } : this._remaining() === 0 ? { kind: "complete-day", name: n } : { kind: "normal" };
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
    ), i = Le(
      n?.attributes?.next_present,
      t
    );
    return i ? U(i, t) : null;
  }
  _renderNotice(e) {
    return d`
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
    return Jt(this.hass);
  }
  _state(e) {
    const n = this.hass?.states?.[e];
    return n && typeof n == "object" ? n : null;
  }
  _childSlug() {
    return sn();
  }
  _boardPath() {
    return w(this._config?.board_path).replace(/\/+$/, "");
  }
  _idleSeconds() {
    const e = y(this._config?.idle_return_seconds, 40);
    return e > 0 ? e : 40;
  }
  _confirmSeconds() {
    const e = y(this._config?.confirm_timeout_seconds, 15);
    return e > 0 ? e : 15;
  }
  _completeSeconds() {
    const e = y(this._config?.complete_screen_seconds, 12);
    return e > 0 ? e : 12;
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
    ), i = b(y(t?.state, 0)), a = b(y(n?.state, 0));
    return { due: i, completed: a };
  }
  _instances() {
    const e = this._childSlug();
    if (!e)
      return [];
    const t = this._state(`sensor.nestquest_${e}_quests_due_today`)?.attributes?.instances;
    if (!Array.isArray(t))
      return [];
    const n = t.map(an).filter((a) => a !== null);
    if (this._optimistic.size === 0)
      return n;
    let i = !1;
    for (const a of n) {
      const r = this._optimistic.get(a.id);
      if (r !== void 0) {
        if (a.state === "completed") {
          this._optimistic.delete(a.id), i = !0;
          continue;
        }
        a.state = "completed", a.overdue = !1, a.completed_at = r;
      }
    }
    return i && (this._optimistic = new Map(this._optimistic)), n;
  }
  _remaining() {
    const e = this._childSlug();
    if (!e)
      return 0;
    const t = this._state(
      `sensor.nestquest_${e}_quests_remaining_today`
    );
    if (t)
      return b(y(t.state, 0));
    const { due: n, completed: i } = this._childCounts(e);
    return b(n - i);
  }
  _partyCounts() {
    const e = this._state(
      "sensor.nestquest_household_quests_due_today"
    ), t = this._state(
      "sensor.nestquest_household_quests_completed_today"
    );
    if (e || t)
      return {
        completed: b(y(t?.state, 0)),
        due: b(y(e?.state, 0))
      };
    const n = this._childSlug(), { due: i, completed: a } = this._childCounts(n);
    return { completed: a, due: i };
  }
  _completeStats() {
    const e = this._childCounts(this._childSlug()).completed, t = this._instances().filter(
      (a) => a.on_time === !0
    ).length, n = b(e - t), i = this._partyCounts();
    return {
      claimed: e,
      onTime: t,
      late: n,
      party: `${i.completed}/${i.due}`
    };
  }
  _completeSub(e) {
    const t = U(this._now, this._timeZone()), { claimed: n, onTime: i, late: a } = this._completeStats();
    return n === 0 ? `${e} sealed the day on ${t}.` : a === 0 ? `${e} claimed every quest on ${t} — all on time.` : i === 0 ? `${e} claimed every quest on ${t} — all late.` : `${e} claimed every quest on ${t} — ${i} on time, ${a} late.`;
  }
  _otherChildren() {
    const e = this.hass?.states;
    if (!e)
      return [];
    const t = this._childSlug(), n = this._timeZone(), i = [];
    for (const a of Object.keys(e)) {
      const r = /^sensor\.nestquest_(.+)_quests_due_today$/.exec(a);
      if (!r || r[1] === "household" || r[1] === t)
        continue;
      const l = r[1], o = e[a]?.attributes ?? {};
      let p = "";
      typeof o.child_name == "string" && o.child_name.trim() ? p = o.child_name.trim() : p = ee(l);
      let u = !0;
      if (typeof o.present == "boolean")
        u = o.present;
      else {
        const _ = this._state(
          `binary_sensor.nestquest_${l}_present_today`
        );
        u = _ === null || String(_.state ?? "").trim().toLowerCase() !== "off";
      }
      const c = this._state(
        `sensor.nestquest_${l}_quests_completed_today`
      ), f = b(y(e[a]?.state, 0)), h = b(y(c?.state, 0));
      let m = null;
      if (!u) {
        const _ = this._state(
          `binary_sensor.nestquest_${l}_present_today`
        ), x = Le(
          _?.attributes?.next_present,
          n
        );
        m = x ? Xt(x, n) : null;
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
    return i.sort((a, r) => a.name.localeCompare(r.name));
  }
  _renderHeader(e) {
    const t = this._childSlug(), n = e.kind === "away", i = n ? e.name : this._childName(t) ?? (t ? ee(t) : null), { due: a, completed: r } = this._childCounts(t), l = this._remaining(), o = this._partyCounts(), p = i ? `${i}'s Quest Log` : "Quest Log", u = (i?.charAt(0) || "?").toUpperCase();
    return d`
      <header class="header">
        <span class="crest${n ? " away" : g}" aria-hidden="true">
          <span class="crest-face">
            <span class="initial">${u}</span>
          </span>
        </span>
        <div class="titles">
          <h1 class="title">${p}</h1>
          <p class="sub">
            ${U(this._now, this._timeZone())} ·
            ${n ? "On travels" : `${r} of ${a} claimed`}
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
                    Party progress · ${o.completed} of ${o.due} today
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
      (l, o) => (l.due_time ?? "99:99").localeCompare(o.due_time ?? "99:99")
    ), i = t.filter(
      (l) => l.state === "completed"
    ), a = t.length;
    let r = g;
    if (a > 0) {
      const o = 644 - (e.key === "afternoon" && this._otherChildren().length > 0 ? 160 : 0), p = Math.min(
        24,
        Math.max(8, Math.floor((o - a * 74) / Math.max(a - 1, 1)))
      ), u = Math.min(
        116,
        Math.max(58, Math.floor((o - (a - 1) * p) / a))
      ), c = Math.max(56, Math.min(72, u - 2));
      let f = `--nq-p-quest-gap: ${p}px; --nq-p-quest-min-height: ${u}px; --nq-p-button-height: ${c}px`;
      if (a >= 5) {
        const h = Math.max(0, Math.min(22, Math.floor((u - c - 2) / 2))), m = Math.max(44, Math.min(64, u - 2 * h - 2));
        f += `; --nq-p-quest-pad: ${h}px; --nq-p-tile-size: ${m}px`;
      }
      r = f;
    }
    return d`
      <section
        class="column"
        aria-label="${e.name} quests"
        style=${r}
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
          ${Te(
      n,
      (l) => l.id,
      (l) => this._renderQuest(l, !1, 0)
    )}
          ${Te(
      i,
      (l) => l.id,
      (l, o) => this._renderQuest(l, !0, o)
    )}
          ${e.key === "afternoon" ? this._renderRollup() : g}
        </div>
      </section>
    `;
  }
  _renderQuest(e, t, n) {
    if (t) {
      const r = Oe[n % Oe.length], l = e.completed_at ? Yt(e.completed_at, this._timeZone()) : "";
      return d`
        <div class="quest sealed" data-instance-id=${e.id}>
          <span class="tile" aria-hidden="true">${Ee(e.icon, te)}</span>
          <div class="body">
            <span class="quest-title">${e.title}</span>
            <span class="meta">
              ${l ? `Claimed ${l}` : "Claimed"}
            </span>
          </div>
          <span
            class="seal"
            aria-hidden="true"
            style="--seal-rot: ${r}deg"
          >
            ${D}
          </span>
        </div>
      `;
    }
    const i = tn(e.due_time), a = e.overdue ? {
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
        data-instance-id=${e.id}
        aria-label="Complete ${e.title}"
        @click=${() => this._openConfirm(e.id)}
        @keydown=${(r) => {
      (r.key === "Enter" || r.key === " ") && (r.preventDefault(), this._openConfirm(e.id));
    }}
      >
        <span class="tile" aria-hidden="true">${Ee(e.icon, te)}</span>
        <div class="body">
          <span class="quest-title">${e.title}</span>
          <span class="meta ${a.late ? "late" : g}">${a.text}</span>
        </div>
        <button
          class="complete"
          type="button"
          @click=${() => this._openConfirm(e.id)}
        >
          ${D}
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
    return d`
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
    const t = Pe.find((n) => n.key === e.window);
    return d`
      <div class="scrim" @click=${() => this._closeConfirm()}>
        <div
          class="dialog"
          role="dialog"
          aria-modal="true"
          @click=${(n) => n.stopPropagation()}
        >
          <div class="dialog-header">
            <span class="dialog-tile" aria-hidden="true">${te}</span>
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
              ${hn}
              <span>Not yet</span>
            </button>
            <button
              class="confirm-button do-complete"
              type="button"
              @click=${() => this._confirmComplete()}
            >
              ${D}
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
    const e = this._confirm === null ? void 0 : this._instances().find(
      (t) => t.id === this._confirm
    );
    this._closeConfirm(), !(!e || e.state !== "open") && this._completeQuest(e);
  }
  /** Seal first, ask the service second: the seal is stamped and the column
   *  re-sorted immediately (PANEL-SPEC §4); a service failure reverts the
   *  card and raises the parchment toast. */
  async _completeQuest(e) {
    if (this._optimistic.has(e.id))
      return;
    const t = (/* @__PURE__ */ new Date()).toISOString();
    this._optimistic = new Map(this._optimistic).set(e.id, t);
    try {
      await this._callCompleteQuest(e);
    } catch {
      const n = new Map(this._optimistic);
      n.delete(e.id), this._optimistic = n, this._showToast(
        "NestQuest could not set the seal just now. Please try again."
      );
    }
  }
  async _callCompleteQuest(e) {
    const t = this.hass;
    if (typeof t?.callService != "function")
      throw new Error("Home Assistant is not connected");
    const n = this._actorChildId(e);
    if (n === null)
      throw new Error("The tapped adventurer is unknown");
    await t.callService.call(t, "nestquest", "complete_quest", {
      instance_id: e.id,
      actor: "panel",
      actor_child_id: n
    });
  }
  /** The tapped profile (decision 9): the instance's own child_id, falling
   *  back to the due sensor's child-level attribute. */
  _actorChildId(e) {
    if (e.child_id !== null)
      return e.child_id;
    const t = this._childSlug(), n = y(
      this._state(`sensor.nestquest_${t}_quests_due_today`)?.attributes?.child_id,
      0
    );
    return n > 0 ? n : null;
  }
  _showToast(e) {
    this._toast = e, this._clearToastTimer(), this._toastTimer = window.setTimeout(() => {
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
        const e = (this._countdown ?? 1) - 1;
        if (e <= 0) {
          this._countdown = 0, this._clearCompleteTimer(), this._returnToBoard();
          return;
        }
        this._countdown = e;
      }, 1e3);
    }
  }
  _clearCompleteTimer() {
    this._completeTimer !== void 0 && (window.clearInterval(this._completeTimer), this._completeTimer = void 0);
  }
  _optionalNumber(e) {
    if (e == null || e === "")
      return null;
    const t = typeof e == "number" ? e : Number(e);
    return Number.isFinite(t) ? t : null;
  }
  _dockWeather() {
    const e = w(this._config?.weather_entity);
    if (!e)
      return null;
    const t = this._state(e);
    if (!t)
      return null;
    const n = String(t.state ?? "").trim();
    if (!n || n === "unavailable" || n === "unknown")
      return null;
    const i = t.attributes ?? {};
    let a = null, r = null;
    const l = i.forecast;
    if (Array.isArray(l) && l.length > 0) {
      const o = l[0];
      if (o && typeof o == "object") {
        const p = o;
        a = this._optionalNumber(p.temperature), r = this._optionalNumber(p.templow);
      }
    }
    return {
      condition: n,
      temperature: this._optionalNumber(i.temperature),
      high: a,
      low: r
    };
  }
  _renderDock() {
    const e = this._dockWeather();
    if (!e)
      return d`
        <div class="dock">
          <span class="date">${U(this._now, this._timeZone())}</span>
          <span class="divider"></span>
          <span class="clock">${en(this._now, this._timeZone())}</span>
        </div>
      `;
    const t = ln(e.condition), n = cn(e.condition, t), i = e.temperature === null ? g : d`<span class="temp">${Math.round(e.temperature)}°</span>`, a = e.high === null || e.low === null ? null : `${Math.round(e.high)}° / ${Math.round(e.low)}°`;
    return d`
      <div class="dock">
        ${bn}
        ${i}
        <span class="divider"></span>
        <span class="condition">
          ${a === null ? t : `${t} · ${a}`}
        </span>
        <span class="divider"></span>
        <span class="condition">${n}</span>
      </div>
    `;
  }
  _returnToBoard() {
    const e = this._boardPath();
    e && (window.history.pushState(null, "", e), window.dispatchEvent(new Event("location-changed")));
  }
  _stopClock() {
    this._clockTimer !== void 0 && (window.clearInterval(this._clockTimer), this._clockTimer = void 0);
  }
  _onActivity = () => {
    this._logView().kind !== "complete-day" && this._armIdle(), this._confirm !== null && this._armConfirmTimer();
  };
}
customElements.define("nestquest-quest-log-card", kn);
le({
  type: "nestquest-quest-log-card",
  name: "NestQuest Quest Log",
  description: "One child's daily quests, grouped by window."
});
const $n = ":host{--nq-brand-blue: #3B3AB8;--nq-brand-purple: #A035CC;--nq-brand-gradient: linear-gradient(135deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-brand-gradient-h: linear-gradient(90deg, var(--nq-brand-blue), var(--nq-brand-purple));--nq-a-page: #F4F4F6;--nq-a-surface: #FFFFFF;--nq-a-surface-subtle: #FAFAFA;--nq-a-selected: #EBEBF8;--nq-a-border: #E4E4EA;--nq-a-divider: #EDEDF1;--nq-a-ink: #18181D;--nq-a-ink-secondary: #52525E;--nq-a-ink-tertiary: #70707E;--nq-a-success: #15803D;--nq-a-danger: #DC2626;--nq-a-danger-strong: #B91C1C;--nq-a-danger-bg: #FEE2E2;--nq-a-warning-ink: #92400E;--nq-a-warning-ink-2: #78350F;--nq-a-warning-bg: #FEF3C7;--nq-a-warning-border: rgba(217,119,6,.35);--nq-a-info-bg: #DBEAFE;--nq-a-info-ink: #1E3A8A;--nq-a-info-icon: #1D4ED8;--nq-a-reversal: #7D28A0;--nq-a-font: Nunito, system-ui, sans-serif;--nq-a-size-screen: 24px;--nq-a-size-hero: 32px;--nq-a-size-card-title: 19px;--nq-a-size-stat: 22px;--nq-a-size-row: 13.5px;--nq-a-size-meta: 11px;--nq-a-size-label: 10px;--nq-a-track-label: .1em;--nq-a-density-page-pad: 14px 16px 92px;--nq-a-density-gap: 10px;--nq-a-density-card-pad: 13px;--nq-a-density-row-pad: 11px 13px;--nq-a-density-radius: 8px;--nq-a-density-shadow: none;--nq-a-tabbar-height: 70px;--nq-a-tap-min: 44px;--nq-a-radius-pill: 9999px;--nq-a-radius-sheet: 20px 20px 0 0;--nq-a-sheet-shadow: 0 -8px 28px rgba(9,9,11,.18);--nq-a-progress-height: 6px;--nq-ease-out: cubic-bezier(0, 0, .2, 1);--nq-dur-micro: .12s;--nq-dur-base: .2s;--nq-dur-modal: .35s}";
class qn extends M {
  static properties = {
    hass: { attribute: !1 },
    _config: { state: !0 }
  };
  static styles = [v($n)];
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
    return d`<div>NestQuest Admin</div>`;
  }
}
customElements.define("nestquest-admin-card", qn);
le({
  type: "nestquest-admin-card",
  name: "NestQuest Admin",
  description: "Parent phone view for today, tasks, schedule, and history."
});
function We(s) {
  return typeof s == "string" ? s.trim() : "";
}
function Cn(s) {
  if (s === null || typeof s != "object" || Array.isArray(s))
    return "";
  const e = s.slug;
  return typeof e == "string" ? e.trim() : "";
}
function Mn(s) {
  const e = We(s.url_path).replace(/^\/+|\/+$/g, "");
  return e || (window.location.pathname.split("/").filter(Boolean)[0] ?? "");
}
function An(s) {
  if (s === null || typeof s != "object" || Array.isArray(s))
    return "";
  const e = s.name;
  return typeof e == "string" ? e.trim() : "";
}
function Sn(s) {
  const n = s?.states?.["sensor.nestquest_household_quests_due_today"]?.attributes?.child_roster;
  return Array.isArray(n) ? n.map((i) => ({ slug: Cn(i), name: An(i) })).filter((i) => i.slug.length > 0) : [];
}
class Tn {
  static async generate(e, t) {
    const n = `/${Mn(e)}`, i = We(e.weather_entity), a = {
      type: "custom:nestquest-party-board-card",
      quest_log_path: n
    };
    i && (a.weather_entity = i);
    const r = {
      type: "custom:nestquest-quest-log-card",
      board_path: n
    };
    return i && (r.weather_entity = i), {
      views: [
        {
          path: "party",
          title: "The Party",
          type: "panel",
          cards: [a]
        },
        ...Sn(t).map((l) => ({
          path: l.slug,
          title: l.name ? `${l.name}'s Quest Log` : `${l.slug}'s Quest Log`,
          type: "panel",
          cards: [{ ...r }]
        }))
      ]
    };
  }
}
window.customStrategies = window.customStrategies ?? {};
window.customStrategies["nestquest-party"] = Tn;
const zn = "/nestquest-static/nestquest-fonts.css";
if (!document.querySelector('link[data-nq-fonts=""]')) {
  const s = document.createElement("link");
  s.rel = "stylesheet", s.href = zn, s.dataset.nqFonts = "", document.head.appendChild(s);
}

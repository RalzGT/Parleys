/* auth.js: una sola cuenta para el Panel y la Quiniela (Supabase Auth, solo con fetch).
   Necesita config.js cargado antes (SUPABASE_URL y SUPABASE_KEY). */
const Cuenta=(function(){
  const leer=(k,d)=>{try{const v=JSON.parse(localStorage.getItem(k));return v==null?d:v}catch(e){return d}};
  const poner=(k,v)=>{try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}};
  const quitar=k=>{try{localStorage.removeItem(k)}catch(e){}};
  const nube=typeof SUPABASE_URL!=="undefined"&&typeof SUPABASE_KEY!=="undefined"&&!/TU-PROYECTO|TU-CLAVE/.test(SUPABASE_URL+SUPABASE_KEY);
  let ses=leer("pn-ses",null);   // {access_token, refresh_token, expires_at, user:{id,email}, nombre}
  const oyentes=[];
  const avisa=()=>oyentes.forEach(f=>{try{f()}catch(e){console.error(e)}});

  function guarda(j,nombre){
    const mismo=ses&&ses.user&&ses.user.id===j.user.id;
    ses={access_token:j.access_token,refresh_token:j.refresh_token,
      expires_at:j.expires_at||Math.floor(Date.now()/1000)+(j.expires_in||3600),
      user:{id:j.user.id,email:j.user.email},
      nombre:nombre!==undefined?nombre:(mismo&&ses.nombre)||""};
    poner("pn-ses",ses);
  }
  async function authPost(ruta,cuerpo,tk){
    const h={apikey:SUPABASE_KEY,"Content-Type":"application/json"};if(tk)h.Authorization="Bearer "+tk;
    const r=await fetch(SUPABASE_URL+ruta,{method:"POST",headers:h,body:JSON.stringify(cuerpo||{})});
    const t=await r.text();let j=null;try{j=t?JSON.parse(t):null}catch(e){}
    if(!r.ok){const e=new Error((j&&(j.msg||j.message||j.error_description))||("HTTP "+r.status));e.code=j&&(j.error_code||j.code);e.status=r.status;throw e}
    return j;
  }
  async function token(){
    if(!ses)throw new Error("sin sesión");
    if(ses.expires_at-60>Date.now()/1000)return ses.access_token;
    try{const j=await authPost("/auth/v1/token?grant_type=refresh_token",{refresh_token:ses.refresh_token});guarda(j);return ses.access_token}
    catch(e){
      if(e.status>=400&&e.status<500&&e.status!==429){ses=null;quitar("pn-ses");avisa()}
      throw e;
    }
  }
  async function rest(ruta,opt){
    opt=opt||{};const tk=await token();
    const r=await fetch(SUPABASE_URL+"/rest/v1/"+ruta,{method:opt.method||"GET",headers:Object.assign({apikey:SUPABASE_KEY,Authorization:"Bearer "+tk,"Content-Type":"application/json"},opt.headers||{}),body:opt.body});
    const t=await r.text();
    if(!r.ok)throw new Error(r.status+" "+t.slice(0,120));
    return t?JSON.parse(t):null;
  }

  /* El nombre se guarda una sola vez en la tabla "perfiles" (así lo ven tus amigos en la quiniela). */
  async function ponNombre(nombre,silencio){
    nombre=String(nombre||"").trim().replace(/\s+/g," ").slice(0,20);
    if(nombre.length<2)throw new Error("Escribe tu nombre (mínimo 2 letras).");
    try{
      await rest("perfiles",{method:"POST",headers:{Prefer:"return=minimal"},body:JSON.stringify([{user_id:ses.user.id,nombre}])});
      ses.nombre=nombre;poner("pn-ses",ses);
    }catch(e){
      if(String(e.message).startsWith("409")){await cargaPerfil();return}
      throw e;
    }
    if(!silencio)avisa();
  }
  async function cargaPerfil(){
    if(!ses)return;
    try{
      const f=await rest("perfiles?select=nombre&user_id=eq."+encodeURIComponent(ses.user.id));
      if(f&&f[0]){ses.nombre=f[0].nombre;poner("pn-ses",ses);return}
      // Cuentas de la versión anterior: el nombre estaba guardado dentro de los datos del panel
      const d=await rest("panel?select=datos&user_id=eq."+encodeURIComponent(ses.user.id));
      const n=d&&d[0]&&d[0].datos&&d[0].datos.perfil&&String(d[0].datos.perfil.n||"").trim();
      if(n&&n.length>=2)await ponNombre(n,true);
    }catch(e){}
  }

  async function entrar(email,pw){
    const j=await authPost("/auth/v1/token?grant_type=password",{email,password:pw});
    guarda(j);await cargaPerfil();avisa();
  }
  async function crear(email,pw,nombre){
    const j=await authPost("/auth/v1/signup",{email,password:pw,data:{nombre}});
    if(!j||!j.access_token)return"confirmar";
    guarda(j,"");
    try{await ponNombre(nombre,true)}catch(e){}
    avisa();return"ok";
  }
  async function salir(){
    try{if(ses)await authPost("/auth/v1/logout",{},ses.access_token)}catch(e){}
    ses=null;quitar("pn-ses");quitar("pn-estado");avisa();   // pn-estado = copia de los datos del panel en este dispositivo
  }
  function msgErr(e){
    const c=e.code||"",m=String(e.message||"").toLowerCase();
    if(c==="invalid_credentials"||m.includes("invalid login"))return"Correo o contraseña incorrectos.";
    if(c==="user_already_exists"||m.includes("already registered"))return"Ese correo ya tiene cuenta. Usa «Entrar».";
    if(c==="weak_password"||m.includes("password should"))return"La contraseña es muy débil (mínimo 6 caracteres).";
    if(c==="email_not_confirmed")return"Tu correo todavía no está confirmado.";
    if(c==="signup_disabled")return"Las cuentas nuevas están desactivadas en este proyecto.";
    if(c==="over_request_rate_limit"||c==="over_email_send_rate_limit"||e.status===429)return"Demasiados intentos. Espera un momento.";
    if(e.status===undefined&&/Failed to fetch|NetworkError|Load failed/i.test(String(e.message)))return"No pude conectar. Revisa tu internet.";
    return e.message;
  }

  return{nube,get ses(){return ses},entrar,crear,salir,ponNombre,cargaPerfil,rest,token,msgErr,alCambiar:f=>oyentes.push(f)};
})();

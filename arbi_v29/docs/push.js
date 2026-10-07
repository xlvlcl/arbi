(() => {
  const $ = id => document.getElementById(id);
  const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent || "");
  const isStandalone = window.matchMedia?.("(display-mode: standalone)")?.matches || window.navigator.standalone === true;
  let deferredInstallPrompt = null;
  let oneSignalReady = false;

  function setText(id, text){ const el=$(id); if(el) el.textContent=text; }
  function show(id, yes=true){ const el=$(id); if(el) el.hidden=!yes; }
  function appId(){ return String(window.ARBI_ONESIGNAL_APP_ID || "").trim(); }

  function setInstallState(){
    if(isStandalone){
      setText("installStatus", "Zainstalowana");
      const b=$("installAppBtn"); if(b){b.textContent="✓ Aplikacja zainstalowana"; b.disabled=true;}
      show("iosInstallHelp", false);
      return;
    }
    setText("installStatus", isIOS ? "Dodaj do ekranu głównego" : "Gotowa do instalacji");
    if(isIOS) show("iosInstallHelp", true);
  }

  async function installApp(){
    if(isStandalone) return;
    if(isIOS){
      show("iosInstallHelp", true);
      $("iosInstallHelp")?.scrollIntoView({behavior:"smooth", block:"center"});
      return;
    }
    if(deferredInstallPrompt){
      deferredInstallPrompt.prompt();
      try{ await deferredInstallPrompt.userChoice; }catch{}
      deferredInstallPrompt=null;
      setInstallState();
      return;
    }
    alert("Jeśli nie widzisz instalacji: w Chrome otwórz menu ⋮ i wybierz „Zainstaluj aplikację” lub „Dodaj do ekranu głównego”.");
  }

  async function refreshPushState(OneSignal){
    const supported = !!OneSignal?.Notifications?.isPushSupported?.();
    if(!supported){
      setText("pushStatus", "Brak obsługi na tym urządzeniu");
      const b=$("enablePushBtn"); if(b) b.disabled=true;
      return;
    }
    if(isIOS && !isStandalone){
      setText("pushStatus", "Najpierw zainstaluj aplikację");
      const b=$("enablePushBtn"); if(b){b.disabled=false; b.textContent="1. Zainstaluj aplikację";}
      return;
    }
    const permission = Notification.permission;
    const optedIn = Boolean(OneSignal?.User?.PushSubscription?.optedIn);
    const subscriptionId = String(OneSignal?.User?.PushSubscription?.id || "");
    if(permission === "granted" && optedIn){
      setText("pushStatus", subscriptionId ? "Aktywne • urządzenie zapisane" : "Powiadomienia aktywne");
      const b=$("enablePushBtn"); if(b){b.disabled=false;b.textContent="✓ Powiadomienia włączone";}
      document.body.classList.add("push-enabled");
      return;
    }
    if(permission === "granted" && !optedIn){
      setText("pushStatus", "Zgoda jest • subskrypcja nieaktywna");
      const b=$("enablePushBtn"); if(b){b.disabled=false;b.textContent="Dokończ włączanie push";}
      document.body.classList.remove("push-enabled");
      return;
    }
    if(permission === "denied"){
      setText("pushStatus", "Zablokowane w ustawieniach telefonu");
      const b=$("enablePushBtn"); if(b){b.disabled=true;b.textContent="Powiadomienia zablokowane";}
      return;
    }
    setText("pushStatus", "Wyłączone");
    const b=$("enablePushBtn"); if(b){b.disabled=false;b.textContent="🔔 Włącz powiadomienia";}
  }

  async function enablePush(){
    if(isIOS && !isStandalone){
      await installApp();
      return;
    }
    if(!appId()){
      setText("pushStatus", "Brak konfiguracji OneSignal");
      alert("Najpierw dodaj ONESIGNAL_APP_ID i ONESIGNAL_API_KEY w GitHub Secrets.");
      return;
    }
    window.OneSignalDeferred = window.OneSignalDeferred || [];
    window.OneSignalDeferred.push(async OneSignal => {
      try{
        await OneSignal.Notifications.requestPermission();
        if(Notification.permission === "granted"){
          try{ await OneSignal.User.PushSubscription.optIn?.(); }
          catch(err){ console.warn("OneSignal optIn warning", err); }
        }
        await refreshPushState(OneSignal);
      }catch(err){
        console.error("Push permission error", err);
        setText("pushStatus", "Nie udało się włączyć");
      }
    });
  }

  window.addEventListener("beforeinstallprompt", e => {
    e.preventDefault();
    deferredInstallPrompt = e;
    setText("installStatus", "Gotowa do instalacji");
  });
  window.addEventListener("appinstalled", () => {
    deferredInstallPrompt = null;
    setInstallState();
  });

  document.addEventListener("DOMContentLoaded", () => {
    setInstallState();
    $("installAppBtn")?.addEventListener("click", installApp);
    $("enablePushBtn")?.addEventListener("click", enablePush);
    $("headerPushBtn")?.addEventListener("click", () => {
      document.querySelector('[data-view="app"]')?.click();
      setTimeout(()=>$("enablePushBtn")?.scrollIntoView({behavior:"smooth", block:"center"}),100);
    });

    if(!appId()){
      setText("pushStatus", "Wymaga konfiguracji OneSignal");
      return;
    }

    window.OneSignalDeferred = window.OneSignalDeferred || [];
    window.OneSignalDeferred.push(async OneSignal => {
      try{
        const basePath = new URL(".", window.location.href).pathname;
        await OneSignal.init({
          appId: appId(),
          serviceWorkerPath: `${basePath}OneSignalSDKWorker.js`,
          serviceWorkerParam: { scope: basePath },
          notifyButton: { enable: false },
          allowLocalhostAsSecureOrigin: false,
        });
        oneSignalReady = true;
        await refreshPushState(OneSignal);
        OneSignal.Notifications.addEventListener("permissionChange", () => refreshPushState(OneSignal));
        OneSignal.User.PushSubscription.addEventListener?.("change", () => refreshPushState(OneSignal));
      }catch(err){
        console.error("OneSignal init error", err);
        setText("pushStatus", "Błąd konfiguracji push");
      }
    });
  });
})();

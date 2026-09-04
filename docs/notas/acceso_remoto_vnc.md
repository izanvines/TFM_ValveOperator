# Acceso remoto a la workstation (TurboVNC)

Manual para conectarte al escritorio remoto de `tr-robotics-WorkStation` sin pasar por xrdp (xrdp tiene un bug conocido que deja el escritorio congelado/negro con GNOME — por eso usamos TurboVNC).

No hace falta saber nada de Linux para seguir esto, solo copiar y pegar los comandos.

---

## 0. Antes de empezar (solo una vez, lo hace un admin)

Para que tu sesión use la GPU de verdad (necesario para que Isaac Sim vaya fluido), tu usuario tiene que pertenecer a los grupos `video` y `render`. Pide a un admin que ejecute, con tu nombre de usuario:

```
sudo usermod -aG video,render TU_USUARIO
```

Esto solo se hace una vez. Después de que te añadan al grupo, **cierra tu sesión SSH y vuelve a entrar** (el cambio no se aplica hasta que abras una conexión nueva).

---

## 1. Poner tu contraseña de VNC (solo la primera vez)

Esta contraseña es solo para el visor VNC, **no** es tu contraseña de Linux. Conéctate por SSH a la máquina y ejecuta:

```
/opt/TurboVNC/bin/vncpasswd
```

Te pedirá:
- Una contraseña (la que quieras, es solo para tu VNC)
- Repetirla
- "Would you like to enter a view-only password?" → responde `n`

---

## 1.5 (Recomendado) Desactiva el bloqueo automático

Las sesiones VNC tienen un fallo conocido: cuando GNOME se bloquea solo por inactividad, a veces se queda **"pillado"** y no acepta ninguna contraseña — ni la tuya de Linux ni nada — hasta que alguien lo desbloquea a mano desde fuera. Para evitarlo del todo, desactiva el bloqueo automático en tu cuenta (se hace una vez).

⚠️ **Importante: ejecuta esto desde una terminal abierta DENTRO de tu escritorio VNC** (por ejemplo, abre una app de terminal desde el propio escritorio remoto), **no desde tu sesión SSH normal**. Si lo ejecutas por SSH desde fuera, el comando puede parecer que funciona (no da error) pero no se aplica de verdad a tu escritorio — cada sesión gráfica tiene su propio canal de configuración interno, y el de una SSH normal es distinto al de tu escritorio VNC.

```
dconf write /org/gnome/desktop/session/idle-delay "uint32 0"
dconf write /org/gnome/desktop/screensaver/lock-enabled "false"
```

Comprueba que se aplicó de verdad, en esa misma terminal:
```
dconf read /org/gnome/desktop/session/idle-delay
```
Debe devolver `uint32 0`. Si devuelve vacío, no se aplicó — asegúrate de estar en una terminal dentro del escritorio remoto, no por SSH.

Es tu sesión personal, ya protegida por el túnel SSH + la contraseña de VNC, así que el riesgo extra es bajo. Con esto tu sesión ya no se bloqueará sola nunca.

---

## 2. Arrancar tu servidor VNC

Cada vez que quieras usar el escritorio remoto (si no lo tienes ya arrancado), ejecuta por SSH:

```
/opt/TurboVNC/bin/vncserver -geometry 1920x1080 -depth 24
```

Te va a contestar algo como:

```
Desktop 'TurboVNC: tr-robotics-WorkStation:2 (TU_USUARIO)' started on display tr-robotics-WorkStation:2
```

Fíjate en el número después de los dos puntos (`:2` en el ejemplo). Tu puerto de conexión es **5900 + ese número**. En este ejemplo: `5902`.

> Si ya lo tenías arrancado de antes, no hace falta repetir este paso — solo tienes que conectar (paso 3). Para comprobar si ya tienes uno corriendo: `/opt/TurboVNC/bin/vncserver -list`

---

## 3. Conectar desde tu PC (Windows)

### 3.1 Abre un túnel SSH

En PowerShell, sustituyendo `TU_USUARIO` y el puerto que te tocó a ti:

```
ssh -L 5902:localhost:5902 TU_USUARIO@<IP_ESTACION>
```

Deja esa ventana abierta mientras uses el escritorio remoto (el túnel vive mientras esa conexión SSH esté abierta).

### 3.2 Abre un visor VNC

No sirve el navegador. Necesitas una aplicación de "VNC Viewer". Si no puedes instalar programas, hay versiones portables (un único `.exe`, sin instalador):

- **TigerVNC Viewer** (portable, recomendado) -> https://sourceforge.net/projects/tigervnc/files/stable/1.16.2/vncviewer64-1.16.2.exe/download
- **TurboVNC Viewer** (mismo proyecto que el servidor)

### 3.3 Conecta

En el visor, en el campo de servidor pon:

```
localhost:5902
```

(usando tu propio puerto, no necesariamente el 5902 del ejemplo)

Te pedirá la contraseña que pusiste en el paso 1 (la de VNC, no la de Linux).

---

## Reglas de oro (para no romper la sesión)

- ❌ **Nunca hagas "Cerrar sesión" desde el menú de GNOME dentro del escritorio remoto.** Esto mata el servidor VNC entero, no solo tu sesión, y hay que volver a arrancarlo desde cero (paso 2).
- ✅ Para "salir", simplemente **cierra la ventana del visor VNC**. Tu sesión se queda esperando tal cual, y la próxima vez conectas directamente (paso 3), sin repetir el paso 2.
- Tu sesión es tuya: no hace falta compartir usuario con nadie. Cada compañero debería tener su propio usuario y su propio puerto VNC.

---

## Solución de problemas

**Pantalla negra nada más conectar**
Espera unos 10-15 segundos, GNOME tarda un poco en arrancar. Si sigue negra después de un rato, contacta con un admin.

**Me pide contraseña y no entra / veo un candado**
Es la pantalla de bloqueo de GNOME, y pide tu **contraseña de Linux** (no la de VNC). Si escribes bien la contraseña y aun así no entra, es el bug conocido de sesión "pillada" — no hay contraseña que lo arregle desde el visor. Aplica el paso 1.5 para que no te vuelva a pasar. Mientras tanto, pide a un admin que lo desbloquee desde una sesión SSH con:
```
loginctl unlock-session c6
```
(el nombre de la sesión puede variar; se ve con `loginctl list-sessions`)

**No puedo conectar, "connection refused"**
Probablemente tu servidor VNC no está arrancado (o se cayó). Repite el paso 2 y usa el puerto nuevo que te indique.

**Quiero parar mi servidor VNC**
```
/opt/TurboVNC/bin/vncserver -kill :2
```
(cambia el `:2` por tu número de display)

**`ls` en mi home da "cannot access 'thinclient_drives': Transport endpoint is not connected"**
Resto inofensivo de una sesión de **xrdp** (no de VNC) que se cerró de golpe — `thinclient_drives` es el punto donde xrdp monta tus discos de Windows, y se queda "colgado" si esa sesión muere sin avisar. No afecta a nada más. Se limpia con:
```
fusermount -u ~/thinclient_drives
```

---

## Firefox (y otras apps snap) no abren en el escritorio remoto

**Causa:** Firefox en esta máquina es un *snap*. Los snap exigen que la sesión gráfica esté registrada como una sesión de login "de verdad" ante systemd. Las sesiones VNC (arrancadas a mano con `vncserver`, sin pasar por un gestor de login) no cumplen ese requisito, así que el snap se niega a abrir: haces clic, sale el cursor de carga, y no pasa nada.

Se descartó arreglar esto a nivel de systemd/PAM (tocaría el arranque de sesión compartido por todos los usuarios y es terreno donde ya hemos tenido bugs de sesión hoy). Las dos soluciones válidas son estas dos.

### Opción A — Firefox real solo para tu usuario (sin sudo, recomendada por defecto)

Descarga el Firefox oficial de Mozilla (binario, no-snap) a tu propia carpeta. No afecta a nadie más.

```
mkdir -p ~/.local/opt
curl -sL -o /tmp/firefox.tar.xz "https://download.mozilla.org/?product=firefox-latest-ssl&os=linux64&lang=es-ES"
tar -xJf /tmp/firefox.tar.xz -C ~/.local/opt/
rm /tmp/firefox.tar.xz
```

Crea el lanzador para que aparezca como app normal (buscador de GNOME, tecla Super):

```
mkdir -p ~/.local/share/applications
cat > ~/.local/share/applications/firefox-real.desktop << EOF
[Desktop Entry]
Name=Firefox
Comment=Navegador web (instalación local, no-snap)
Exec=$HOME/.local/opt/firefox/firefox %u
Terminal=false
Type=Application
Icon=$HOME/.local/opt/firefox/browser/chrome/icons/default/default128.png
Categories=Network;WebBrowser;
MimeType=text/html;text/xml;application/xhtml+xml;x-scheme-handler/http;x-scheme-handler/https;
StartupWMClass=firefox
EOF
update-desktop-database ~/.local/share/applications/
```

Ábrelo desde el buscador de aplicaciones como "Firefox" — **no** desde el icono del dock, que sigue siendo el snap roto.

**Paso extra necesario: regístralo como navegador predeterminado.** Sin esto, botones tipo "Sign in with Google" en otras apps (Antigravity, etc.) seguirán intentando abrir el snap roto y no harán nada al pulsarlos, aunque tú ya tengas el Firefox real instalado:

```
xdg-settings set default-web-browser firefox-real.desktop
```

Comprueba que se aplicó a los tres esquemas de enlace que usan estos botones de login:

```
xdg-mime query default text/html
xdg-mime query default x-scheme-handler/http
xdg-mime query default x-scheme-handler/https
```

Las tres deben devolver `firefox-real.desktop`. Si alguna no lo hace, fíjala a mano:

```
xdg-mime default firefox-real.desktop text/html
xdg-mime default firefox-real.desktop x-scheme-handler/http
xdg-mime default firefox-real.desktop x-scheme-handler/https
```

### Opción B — Firefox real para todos (una vez, necesita sudo, afecta a todo el sistema) - NO HACER (INSTALAR POR USUARIO NO ROMPE NADA CONFIRMADO)

Reemplaza el snap por el paquete oficial de Mozilla vía apt, para toda la máquina. Solo lo debe ejecutar un admin, y solo si el problema se repite con varios usuarios:

```
sudo install -d -m 0755 /etc/apt/keyrings
wget -q https://packages.mozilla.org/apt/repo-signing-key.gpg -O- | sudo tee /etc/apt/keyrings/packages.mozilla.org.asc > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" | sudo tee -a /etc/apt/sources.list.d/mozilla.list > /dev/null
printf '\nPackage: *\nPin: origin packages.mozilla.org\nPin-Priority: 1000\n' | sudo tee /etc/apt/preferences.d/mozilla
sudo apt update
sudo apt install -y firefox
```

Esto sustituye el paquete transicional del snap por el `.deb` real. Opcional, para limpiar el snap si quedó instalado: `sudo snap remove firefox`.

---

## Referencia rápida

| Qué | Comando |
|---|---|
| Poner contraseña VNC (1 vez) | `/opt/TurboVNC/bin/vncpasswd` |
| Desactivar bloqueo automático (1 vez, recomendado) | `dconf write /org/gnome/desktop/session/idle-delay "uint32 0"` y `dconf write /org/gnome/desktop/screensaver/lock-enabled "false"` |
| Arrancar servidor | `/opt/TurboVNC/bin/vncserver -geometry 1920x1080 -depth 24` |
| Ver si ya tengo uno corriendo | `/opt/TurboVNC/bin/vncserver -list` |
| Parar servidor | `/opt/TurboVNC/bin/vncserver -kill :N` |
| Túnel desde Windows | `ssh -L 590N:localhost:590N TU_USUARIO@<IP_ESTACION>` |
| Servidor en el visor VNC | `localhost:590N` |
| Registrar Firefox real como predeterminado | `xdg-settings set default-web-browser firefox-real.desktop` |
| Limpiar montaje `thinclient_drives` colgado | `fusermount -u ~/thinclient_drives` |

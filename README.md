# Pear Car Radio — MVP singleplayer

Controla la canción **o la playlist que ya tengas abierta en Pear Desktop** desde la emisora **Pear FM** de la radio de un coche en Project Zomboid Build 42.20+. El audio se reproduce en Pear; no se descarga ni se retransmite música. Versión 0.3.1, experimental.

## Preparar y jugar

1. Abre Pear Desktop / YouTube Music. La instalación detectada en este equipo es 3.12.0. Selecciona una canción o playlist y comprueba que se escucha.
2. En el menú de plugins de Pear, activa **API Server**. Configura el hostname como `127.0.0.1`, puerto `26538` y conserva la autenticación **Auth at first**. No necesitas abrir puertos del router. Su documentación aparece en <http://127.0.0.1:26538/swagger> cuando está activo.
3. Con Zomboid cerrado, ejecuta en PowerShell: `powershell -ExecutionPolicy Bypass -File .\Instalar-Mod.ps1`. Solo copia este mod a tu carpeta local; no toca los archivos del juego ni activa mods en partidas.
4. Ejecuta **Iniciar-Puente.cmd**. Requiere Python 3.9 o posterior; no necesita instalar paquetes. Acepta en Pear la solicitud de **PZPearCarRadio**. No compartas el token de Pear ni tus credenciales.
5. Abre Zomboid y activa **Pear Car Radio (SP MVP)**. En una partida existente usa **Cargar → Más → Elegir mods**; es recomendable una partida de prueba.
6. Sube a un coche con radio instalada y batería. Abre su radio desde el menú del vehículo (`V`) y enciéndela. En **Channel**, selecciona **94.0 MHz Pear FM** y pulsa **Tune in**. También puedes usar el botón **Sintonizar Pear FM** del panel Pear Car Radio.
7. Usa el volumen normal de la radio y los botones **Anterior / Pausa / Siguiente** del panel Pear.

La frecuencia sintonizada se guarda con la radio. Cambiar a otra emisora pausa Pear y devuelve el audio normal del juego; el botón **Volver a la emisora anterior** hace ese cambio directamente. **Al bajar del coche la música sigue sonando** si la radio permanece encendida, con energía y en Pear FM. Al morir o salir de la partida, el puente pausa lo que controlaba. Si el juego deja de enviar señales durante 3 segundos, el puente también pausa. Al pausar Zomboid puede haber ese pequeño retraso. Para detener el puente usa **Ctrl+C** en su ventana; un cierre forzado del proceso puede impedir la pausa final.

Fuera del coche, el volumen disminuye con la distancia: al 100% se oye hasta unas 35 casillas; a menor volumen, el alcance también disminuye. Dentro se mantiene el volumen seleccionado. Fuera del alcance, la canción sigue avanzando en silencio mientras el coche esté cargado en el mundo. Si el juego descarga o elimina el coche, se pausa y se olvida esa fuente hasta que vuelvas a subir a él. El mod recuerda solo el último coche usado durante esta sesión; entrar en otro coche cambia la fuente y no mezcla ambas radios. No descubre automáticamente coches lejanos al cargar una partida a pie.

Pear FM usa 94.0 MHz por defecto y elige otra frecuencia libre de la banda FM si otra emisora ocupa esa posición. No sobrescribe emisoras de otros mods. Se agrega un preset al abrir la radio; si todos los espacios están llenos, conserva los existentes y permite sintonizar con el botón del panel. Libera un espacio y vuelve a abrir la radio para añadir el preset al desplegable.

Mientras el mod sigue el coche sintonizado en Pear FM, dentro o fuera, mantiene una señal local en esa radio para evitar que el motor genere texto de estática como `<wzzt>`. No modifica el diálogo de personajes ni el de otras radios, y no accede a `ChatElement`, que no está expuesto a Lua en B42.21. Si el motor no permite actualizar esa señal, el mod desactiva solo esa función y mantiene los controles y el puente. El texto de estática que ya estuviera en pantalla puede durar hasta que expire normalmente. Es una emisora local de control: no emite música por el sistema de transmisiones del juego ni añade MP. La señal local también utiliza la reacción de ruido nativa de una radio encendida.

**La música atrae zombis**: activado por defecto, configurable en **Opciones → Mods → Pear Car Radio**. Agrega ruido en la posición del coche solo cuando Pear confirma reproducción. Alcance experimental: hasta 35 casillas al 100%; no garantiza una cantidad de zombis. Alejarte baja lo que escuchas tú, pero no reduce el ruido que produce el coche para los zombis. Se suma al ruido normal del coche/radio y debe ajustarse jugando. Silenciar Pear manualmente no cambia automáticamente el ruido: usa el volumen o pausa del coche.

## Límites actuales

- Solo singleplayer, jugador local 0. El mod no añade el panel ni controla Pear en multijugador. Pantalla dividida no soportada.
- Selección de canción/playlist **en Pear**. Pegar un enlace dentro del juego queda pendiente; la propuesta upstream [#4615](https://github.com/pear-devs/pear-desktop/pull/4615) aún no está integrada en el código revisado.
- Un coche audible por jugador, con volumen según distancia al salir. Sin sonido direccional, efectos de paredes/ventanas ni mezcla de varias radios. Al sintonizar Pear FM se silencia el emisor de esa radio para evitar voces y estática; se puede desactivar en Opciones → Mods. Al cambiar de emisora se restaura el emisor original.
- Requiere Pear y este puente abiertos. Workshop por sí solo no iniciará el programa auxiliar.
- El puente cambia el volumen de Pear durante el uso y restaura el volumen numérico anterior al dejar de controlar el coche. No restaura la canción/cola ni el estado de reproducción anterior. No modifica el volumen general de Windows.
- Si pausas manualmente en Pear, el mod no pelea continuamente con tu decisión. Usa **Pausa → Seguir** en el coche para reanudar. El estado visual puede tardar alrededor de un segundo más el tiempo de carga de Pear.
- Carga de canciones, acceso a contenido y sesión de Google dependen de Pear. El mod no usa contraseñas de Google.

## Actualizar

Para pasar a 0.3.1, instala la copia nueva y reinicia Zomboid. Corrige el error repetido `attempted index: clear of non-table: zombie.chat.ChatElement` que interrumpía los controles. El puente no cambió en esta versión; puede seguir abierto. Sintoniza Pear FM en el coche y baja con la radio encendida para probar la música exterior y su volumen por distancia.

Cierra Zomboid y el puente (Ctrl+C) y abre de nuevo ambos después de instalar la copia nueva. La versión 0.1.1 usa archivos `.txt`: Build 42.21 bloqueaba silenciosamente la escritura del antiguo `.control`. El archivo `.status` antiguo ya no se utiliza. No basta con volver a abrir la ventana de radio: hay que reiniciar el juego. Despausa la partida para reproducir y cambiar canciones.

## Diagnóstico

| Síntoma | Revisar |
| --- | --- |
| No aparece el mod | Reiniciar Zomboid y activarlo también en la partida; usar Build 42.20+ |
| No aparece el panel | Estar sentado en un vehículo con radio instalada; abrir la ventana de radio y desplegar Pear Car Radio |
| Puente sin conexión | Abrir Pear, habilitar API Server, comprobar puerto/hostname y aceptar PZPearCarRadio |
| Ventana negra dice «Select» y el estado no cambia | Pulsa Esc en esa ventana: seleccionar texto en la consola de Windows puede suspender el puente. La versión actual desactiva QuickEdit al iniciarse; reinicia solo el puente para aplicar ese cambio |
| API responde pero no hay música | Reproducir una canción manualmente en Pear, comprobar batería y radio encendida; pulsar Pausa y Seguir |
| Funciona en el puente pero el juego no lo ve | Ambos deben usar el mismo directorio Zomboid; revisar `Zomboid/Lua/PearCarRadio.status.txt` |
| Error Lua | Revisar `%USERPROFILE%\Zomboid\console.txt` y buscar `PearCarRadio` |

Para un directorio Zomboid personalizado, instala con `-ZomboidDir 'D:\MiZomboid'` y lanza el puente con `Iniciar-Puente.cmd --zomboid-dir "D:\MiZomboid"`. Para otro puerto usa `--port 26539` y el mismo puerto en Pear.

## Desarrollo y comprobación

`python -m unittest discover -s tests -v`

Los tests verifican el protocolo de archivos, las peticiones HTTP y el control de reproducción con un servidor Pear simulado. No sustituyen una prueba con el juego y Pear reales. El puente usa exclusivamente la biblioteca estándar de Python. El mod añade un módulo a `ISRadioWindow` conservando los módulos originales; utiliza las funciones de archivos de Lua del juego para evitar llamadas de red desde el hilo principal.

El intercambio usa `Zomboid/Lua/PearCarRadio.control.txt` y `PearCarRadio.status.txt`. Cada estado tiene sesión, contador y marca final de escritura; las órdenes antiguas o incompletas se descartan. El puente requiere estado fresco para tomar control de Pear y no repite una orden si pierde la respuesta. Pulsaciones muy rápidas pueden combinarse: espera un instante entre cambios de canción. Un bloqueo del sistema impide abrir dos puentes para el mismo directorio Zomboid.

Para ejecutar también el arnés opcional de Lua 5.1: `python -m pip install --target .tools lupa`, luego vuelve a ejecutar los tests. Esa dependencia solo se usa durante el desarrollo; no hace falta para jugar.

Próximas etapas: apertura de canción/playlist por enlace, suavizar volumen por distancia y coordinar canción/tiempo entre clientes MP. El ruido del mundo deberá controlarlo el servidor en esa futura versión.

# Patrones de LaTeX de la plantilla

El capítulo `Ejemplos de uso de LaTeX (QUITAR DE LA MEMROIA)` se ha eliminado de la memoria, tal
como la propia plantilla indica. Se conservan aquí sus patrones porque son **la forma exacta en que
la plantilla espera que se escriban figuras, tablas y código**, y la memoria los reutiliza tal cual
en vez de inventar un estilo propio.

Lo que hay que respetar de cada uno:

- **Figura**: `\caption[texto corto]{texto largo}` — el corto es el que va al índice de figuras. La
  fuente, si la hay, va dentro del propio `\caption` en `\footnotesize{\textit{...}}`.
- **Tabla**: entorno `table*` con `\centering`, `\caption` **antes** del `\begin{tabular}` (al
  revés que en las figuras), y `\makebox[\textwidth]{...}` cuando la tabla es más ancha que la caja
  de texto.
- **Código**: `lstlisting`, ya configurado en el preámbulo para bash (marco, números de línea a la
  izquierda, palabras clave en azul).
- **Notas al pie**: `\footnote{...\label{etiqueta}}` la primera vez y
  `\textsuperscript{\ref{etiqueta}}` para repetirla.

---

```latex
\chapter*{Ejemplos de uso de LaTeX (QUITAR DE LA MEMROIA)}
\label{Ejemplos de uso de LaTeX}

\section*{Ejemplo de uso de notas al pie}
\label{Seguridad general}

El término \emph{seguridad informática} abarca muchos aspectos, y dar una definición de manera genérica es complejo. Debe poderse aplicar a cualquier tipo de sistema informático, y al mismo tiempo describir qué se entiende por seguridad.

Aunque existen diferentes definiciones según la fuente, a continuación se presentan algunos enunciados concisos:

\begin{itemize}

\item ``Es la protección de los datos, de las redes y del suministro eléctrico de un sistema informático.''\footnote{\textit{Definition of computer security.} Encyclopedia. Ziff Davis, PCMag. \url{http://www.pcmag.com/encyclopedia/term/44958/information-security}}

\item ``Disciplina que se ocupa de diseñar normas, procedimientos y técnicas, destinados a conseguir que un sistema de información sea seguro.''\footnote{\url{https://es.wikipedia.org/wiki/Seguridad_informática}\label{segWiki}}

\item ``Área de la informática enfocada en la protección de las infraestructuras computacionales y, especialmente, de la información contenida o que circula por ellas.''\textsuperscript{\ref{segWiki}}

\end{itemize}
 

\section*{Ejemplo de imagen}

Existen tres requisitos fundamentales a tener en cuenta de cara a proteger la información que procesan los sistemas informáticos.
Se trata de: \textit{confidencialidad}, \textit{integridad} y \textit{disponibilidad}. Estos conceptos se refieren al uso, transferencia y almacenamiento de los datos, respectivamente.

En la figura \ref{fig:fundamentos-seguridad} puede verse un esquema con los tres requisitos mencionados.

\begin{figure}[htb] 
\centering
  \includegraphics[width=.55\textwidth]{figuras/c-i-a.png}
  \caption[Elementos principales de seguridad de la información]{Elementos principales de seguridad de la información\\
  \footnotesize{Fuente: \textit{http://geraintw.blogspot.com.es/2012/09/cia-infosec.html}}}
  \label{fig:fundamentos-seguridad}
\end{figure}


\section*{Ejemplo de lista con números}

\begin{enumerate}

\item Confidencialidad:\\
El principio de confidencialidad consiste en asegurar que la información es accesible sólo para aquellos destinatarios que estén autorizados, con independencia de dónde se almacene la información.
La confidencialidad de los datos se implementa mediante mecanismos de control de acceso, tanto físicos (hardware) como  de programación (software).

\item Integridad:\\
La integridad de los datos se refiere a garantizar el estado de la información, protegiéndola de cambios accidentales o malintencionados. Mantener la integridad es esencial para la privacidad, la seguridad y la fiabilidad de los datos almacenados en un sistema.
Las medidas que se utilizan para mitigar posibles fallos en los datos incluyen: copias de seguridad regulares, almacenamiento seguro de esas copias fuera del lugar de trabajo y herramientas de control de integridad.

\item Disponibilidad:\\
La disponibilidad de los datos tiene como objetivo que los usuarios autorizados tengan acceso a la información en el momento que la necesiten. Esto implica garantizar el correcto funcionamiento de los equipos utilizados para almacenar y procesar los datos, de los controles de seguridad para protegerlos, y de los canales de comunicación utilizados para acceder a ellos.

\end{enumerate}


\section*{Una tabla con varias cabeceras}
\label{Ciberseguridad robótica}

La tabla~\ref{tabla1} extiende a los robots sociales y asistenciales la clasificación de criticidad para sistemas industriales, propuesta en \cite{CSSP}.

\begin{table*}[ht]
	\centering
	\caption{Perfiles de seguridad asociados a la robótica}
	\label{tabla1}
	\begin{tabular}{|l|ccc|}
		\cline{2-4}
		\multicolumn{1}{c}{} & \multicolumn{3}{|c|}{Criticidad} \\
		\cline{1-4}
		\multicolumn{1}{|c|}{Perfil} &  Confidencialidad & Integridad & Disponibilidad \\ \hline
		Estación de trabajo (PC) & Alta & Alta 	&  Baja \\
		Equipo para control industrial & Baja & Media & Muy alta \\
		Robots asistenciales & Muy alta & Muy alta & Muy alta \\
		Robots sociales & Muy alta & Media & Baja \\ \hline
	\end{tabular}
\end{table*}


\section*{Descripción de ROS: Robot Operating System}
\label{ROS}

Vistazo general sobre ROS:\\
- Historia y versión actual.\\
- Aplicación: investigación y también robots comerciales.\\
- Arquitectura: componentes básicos y funcionamiento.


\section*{Ejemplo de código fuente}

\vspace{0.5cm}  % Añado espacio vertical extra para separar el código del título de la sección.

\begin{lstlisting}
#!/bin/bash

# VARIABLES GLOBALES:

BASHRC_FILE="$HOME/.bashrc"
HOST_VAR_NAME="ROS_HOSTNAME"
MASTER_VAR_NAME="ROS_MASTER_URI"
ROS_PORT="11311"
HOST_IP=""    # Se asigna por parametro.
MASTER_IP=""  # Se asigna por parametro.
FILENAME="$(basename $0)"

# FUNCIONES:

description() {
if [ $1 -ne 0 ]; then
echo -e "\n  ========"
fi
echo -e "\n  This script adds or modifies $HOST_VAR_NAME and $MASTER_VAR_NAME variables"
echo -e "    in the '~/.bashrc' file of current user.\n"
}
\end{lstlisting}



%*********************************************

```

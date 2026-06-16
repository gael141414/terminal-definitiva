from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import streamlit as st

from modulos.gemini_helper import obtener_api_key_gemini, obtener_modelo_gemini


def aplicar_parche_sqlite():
    """Usa pysqlite3 en despliegues donde sqlite3 del sistema es antiguo."""
    try:
        __import__("pysqlite3")
        sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
    except Exception:
        pass


def obtener_secreto(nombre: str):
    try:
        return st.secrets.get(nombre)
    except Exception:
        return None


def _recortar_contexto(docs, limite_chars: int = 5500) -> str:
    fragmentos = []
    total = 0
    for i, doc in enumerate(docs, start=1):
        origen = doc.metadata.get("source", "Documento local")
        texto = doc.page_content.strip()
        if not texto:
            continue
        bloque = f"[Fuente {i}: {origen}]\n{texto}\n"
        if total + len(bloque) > limite_chars:
            bloque = bloque[: max(0, limite_chars - total)]
        fragmentos.append(bloque)
        total += len(bloque)
        if total >= limite_chars:
            break
    return "\n---\n".join(fragmentos)


def _respuesta_local_extractiva(pregunta: str, docs) -> str:
    if not docs:
        return (
            "No encuentro fragmentos relevantes en la base documental local. "
            "Prueba con una pregunta más concreta sobre valoración, margen de seguridad, deuda, ROIC o filosofía Buffett."
        )

    lineas = [
        "**Modo local sin LLM:** no hay `GROQ_API_KEY` ni proveedor IA remoto activo. "
        "Estos son los fragmentos documentales más relevantes para tu consulta:",
        "",
    ]
    for i, doc in enumerate(docs, start=1):
        origen = doc.metadata.get("source", "Documento local")
        texto = " ".join(doc.page_content.split())[:650]
        lineas.append(f"**Fuente {i}: {origen}**")
        lineas.append(f"> {texto}...")
        lineas.append("")
    lineas.append("Para una respuesta redactada y razonada, configura `GROQ_API_KEY` o `GEMINI_API_KEY`.")
    return "\n".join(lineas)


@dataclass
class MotorChatbotDocumental:
    retriever: object
    provider: str
    llm: object | None = None

    def invoke(self, payload: dict) -> dict:
        pregunta = str(payload.get("input", "")).strip()
        docs = self.retriever.invoke(pregunta)

        if self.provider == "groq" and self.llm is not None:
            contexto = _recortar_contexto(docs)
            prompt = (
                "Eres un asesor financiero experto de Value Investing. Responde en español, "
                "con tablas Markdown cuando ayuden, y usa exclusivamente el contexto documental.\n\n"
                f"Contexto:\n{contexto}\n\nPregunta: {pregunta}"
            )
            respuesta = self.llm.invoke(prompt)
            texto = getattr(respuesta, "content", str(respuesta))
            return {"answer": texto, "context": docs}

        if self.provider == "gemini" and self.llm is not None:
            contexto = _recortar_contexto(docs)
            prompt = (
                "Eres un asesor financiero experto e IA de un terminal de inversión Value Investing. "
                "Responde en español, sé concreto, usa tablas Markdown si comparas datos y basa la respuesta "
                "exclusivamente en el contexto proporcionado. Si falta contexto, dilo claramente.\n\n"
                f"Contexto:\n{contexto}\n\nPregunta del usuario:\n{pregunta}"
            )
            respuesta = self.llm.generate_content(prompt)
            return {"answer": getattr(respuesta, "text", "") or "No se pudo generar respuesta.", "context": docs}

        return {"answer": _respuesta_local_extractiva(pregunta, docs), "context": docs}


@st.cache_resource(show_spinner=False)
def cargar_retriever_documental():
    aplicar_parche_sqlite()

    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain_community.vectorstores import Chroma

    modelo_embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    vectorstore = Chroma(
        persist_directory="./db_inversion",
        embedding_function=modelo_embeddings,
    )
    return vectorstore.as_retriever(search_kwargs={"k": 4})


@st.cache_resource(show_spinner=False)
def cargar_motor_chatbot():
    """Carga el chatbot documental con Groq, Gemini o fallback local."""
    retriever = cargar_retriever_documental()

    groq_api_key = obtener_secreto("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY")
    if groq_api_key:
        try:
            os.environ["GROQ_API_KEY"] = str(groq_api_key)
            from langchain_groq import ChatGroq

            llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.2)
            return MotorChatbotDocumental(retriever=retriever, provider="groq", llm=llm)
        except Exception:
            pass

    if obtener_api_key_gemini():
        modelo_gemini = obtener_modelo_gemini()
        if modelo_gemini is not None:
            return MotorChatbotDocumental(retriever=retriever, provider="gemini", llm=modelo_gemini)

    return MotorChatbotDocumental(retriever=retriever, provider="local", llm=None)


def render_chatbot():
    st.title("Terminal de Inversión: Asistente Value Investing")

    try:
        chatbot_chain = cargar_motor_chatbot()
    except Exception as e:
        st.error("No se pudo cargar la base documental local del chatbot.")
        st.caption(str(e))
        return

    if chatbot_chain.provider == "groq":
        st.success("Chatbot documental activo con Groq.")
    elif chatbot_chain.provider == "gemini":
        st.success("Chatbot documental activo con Gemini.")
    else:
        st.info("Modo local: consulta documental sin IA remota. Configura `GROQ_API_KEY` o `GEMINI_API_KEY` para respuestas generativas.")

    if "mensajes_ia" not in st.session_state:
        st.session_state.mensajes_ia = []

    for mensaje in st.session_state.mensajes_ia:
        with st.chat_message(mensaje["rol"]):
            st.markdown(mensaje["contenido"])

    pregunta = st.chat_input("Pregunta sobre una empresa, valoración, filosofía...")

    if pregunta:
        with st.chat_message("user"):
            st.markdown(pregunta)
        st.session_state.mensajes_ia.append({"rol": "user", "contenido": pregunta})

        with st.chat_message("assistant"):
            with st.spinner("Analizando documentos e historial Value..."):
                try:
                    respuesta_obj = chatbot_chain.invoke({"input": pregunta})
                    texto_respuesta = respuesta_obj["answer"]
                    st.markdown(texto_respuesta)

                    if respuesta_obj.get("context"):
                        with st.expander("📚 Ver documentos fuente utilizados"):
                            for i, doc in enumerate(respuesta_obj["context"], start=1):
                                origen = doc.metadata.get("source", "Documento local")
                                st.caption(f"**Fuente {i}:** {origen}")
                                st.text(doc.page_content[:250] + "...")
                except Exception as e:
                    texto_respuesta = f"No se pudo generar respuesta del chatbot: {e}"
                    st.error(texto_respuesta)

        st.session_state.mensajes_ia.append({"rol": "assistant", "contenido": texto_respuesta})

import streamlit as st
import requests
import numpy as np
import pandas as pd
import time
from datetime import datetime, timedelta

import os
import psutil
from dotenv import load_dotenv

load_dotenv(override=True)

# Configuração da página
st.set_page_config(page_title="🚍 chegadaPyJ / Chegada de veículos", layout="wide")
#st.title("📡 chegadaPyJ / Chegada de veículos")

hide_st_style = """
            <style>
            #bui1 > div > div > ul >ul:nth-child(1) {visibility: hidden;}
            #bui1 > div > div > ul >ul:nth-child(2) {visibility: hidden;}
            #bui1 > div > div > ul >ul:nth-child(4) {visibility: hidden;}
            #bui1 > div > div > ul >ul:nth-child(5) {visibility: hidden;}
            #bui1 > div > div > ul >ul:nth-child(7) {visibility: hidden;}
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

AUTH_URL = "https://consultaviagem.m2mfrota.com.br/AutenticarUsuario"
API_URL = "https://zn4.sinopticoplus.com/servico-dados/api/v1/obterPosicaoVeiculo"

CREDENCIAIS = {
    "usuario": os.getenv("userUsuario"),
    "senha": os.getenv("passwordSenha")
}

# Tenta autenticar e obter o token
@st.cache_data(ttl=1800)  # Cache por 30 minutos
def autenticar_e_obter_token():
    response = requests.post(AUTH_URL, json=CREDENCIAIS)
    if response.status_code == 200:
        data = response.json()
        token = data.get("IdentificacaoLogin") or data.get("Authorization") or data.get("authToken")
        if token:
            return token
        else:
            raise Exception("⚠️ Token não encontrado na resposta da autenticação.")
    else:
        raise Exception(f"Erro na autenticação: {response.status_code} - {response.text}")

# Autenticar
try:
    token = autenticar_e_obter_token()
except Exception as e:
    st.error(str(e))
    st.stop()

headers = {
    "Authorization": token,
    "Content-Type": "application/json"
}

placeholder_tabela = st.empty()
placeholder_mapa = st.empty()

ontem = datetime.now() - timedelta(days=1)
amanha = datetime.now() + timedelta(days=1)
arquivo_ontem_csv = 'chegada_' + ontem.strftime('%Y-%m-%d') + '.csv'
arquivo_amanha_csv = 'chegada_' + amanha.strftime('%Y-%m-%d') + '.csv'

nome_arquivo_csv = 'chegada_' + datetime.now().strftime('%Y-%m-%d') + '.csv'
arquivo_csv = st.file_uploader("Carregar CSV de Chegadas (" + nome_arquivo_csv + ")", type=["csv"])

def formatar_diferenca(diferenca):
    prefixo = 'Atraso de '
    horas = abs(int(diferenca.total_seconds() // 3600))
    minutos = abs(int((diferenca.total_seconds() % 3600) // 60))
    chegada = f'{prefixo}{horas:02d}:{minutos:02d}'
    return f'<font color="red">{chegada}</font>'
    
def formatar_diferencaMenor(diferencaMenor):
    prefixo = 'Chegando em '
    horas = abs(int(diferencaMenor.total_seconds() // 3600))
    minutos = abs(int((diferencaMenor.total_seconds() % 3600) // 60))
    chegada = f'{prefixo}{horas:02d}:{minutos:02d}'
    return f'<font color="green">{chegada}</font>'

if (arquivo_csv) and ((nome_arquivo_csv == arquivo_csv.name) or (arquivo_ontem_csv == arquivo_csv.name) or (arquivo_amanha_csv == arquivo_csv.name)):
    df_csv = pd.read_csv(arquivo_csv)
    print (df_csv)
    i = 0
    while True:
        try:
            response = requests.get(API_URL, headers=headers)

            if response.status_code == 200:
                data = response.json()
                
                if data:
                    veiculos = data.get("veiculos", [])

                    # Filtrar apenas os veículos que não são None
                    veiculos_validos = [v for v in veiculos if v is not None]

                    df = pd.DataFrame(veiculos_validos)
                    df = df.drop(['id_migracao_trajeto', 'hodometro', 'velocidade', 'direcao', 'trajeto'], axis=1)

                    if 'dataHora' in df.columns:
                        df['dataHora'] = pd.to_datetime(df['dataHora'], unit='ms', utc=True)
                        df['dataHora'] = df['dataHora'].dt.tz_convert('America/Sao_Paulo')
                        df['dataHora'] = df['dataHora'].dt.strftime('%Y-%m-%d %H:%M')
                    
                    df["sentido"] = np.where((df['latitude'] >= -3.807708) & (df['latitude'] <= -3.805093) & (df['longitude'] >= -38.469888) & (df['longitude'] <= -38.468058), "dentro", "fora")
                    df['ignicao'] = df['ignicao'].map({1: 'ligada', 0: 'desligada'})

                    df = df[df['sentido'] == 'fora']

                    df.index = df.index + 1

                    df_view = df.drop(columns=["placa", "dataHora", "linha", "ignicao"]).rename(columns={"codigo": "veiculo"})
                    df_view['veiculo'] = df_view['veiculo'].astype(str).str.strip()
                    df_csv['veiculo'] = df_csv['veiculo'].astype(str).str.strip()
                    df_merged = pd.merge(df_view, df_csv, on='veiculo', how='outer')

                    df_merged["local"] = df_merged.apply(
                    lambda row: f"[Mapa](https://www.google.com/maps?q={row['latitude']},{row['longitude']})", axis=1
                    )

                    df_merged = df_merged.dropna()

                    fora = (df_merged['sentido'] == 'fora').sum()

                    df_merged = df_merged.drop(columns=["sentido", "linha", "latitude", "longitude"])
                    df_merged['horachegada'] = pd.to_datetime(df_merged['horachegada'])
                    
                    hora_atual = datetime.now()

                    df_merged['horaatual'] = hora_atual
                    df_merged["diferenca"] = np.where((df_merged['horaatual'] > df_merged['horachegada']), df_merged['horaatual'] - df_merged['horachegada'], df_merged['horachegada'] - df_merged['horaatual'])
                    df_merged['chegada'] = np.where((df_merged['horaatual'] > df_merged['horachegada']), df_merged['diferenca'].apply(formatar_diferenca), df_merged['diferenca'].apply(formatar_diferencaMenor))
                    df_merged = df_merged.drop(columns=["diferenca", "horaatual"])
                    df_merged['horachegada'] = df_merged['horachegada'].dt.strftime('%Y-%m-%d %H:%M')

                    df_final = df_merged.sort_values("horachegada")

                    with placeholder_tabela.container():
                        st.markdown('<h3>📡 chegadaPyJ / Chegada de veículos em ' + arquivo_csv.name[8:8+10] + '</h3>', unsafe_allow_html=True)
                        st.write(df_final.to_markdown(index=False), unsafe_allow_html=True)
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric(label = "Chegadas programadas:", value = fora)

                else:
                    placeholder_tabela.warning("⚠️ Nenhum dado retornado.")
                    placeholder_mapa.empty()

            else:
                placeholder_tabela.error(f"Erro {response.status_code}: {response.text}")
                placeholder_mapa.empty()

        except Exception as e:
            placeholder_tabela.error(f"Erro na requisição: {e}")
            placeholder_mapa.empty()

        time.sleep(10)
    
    

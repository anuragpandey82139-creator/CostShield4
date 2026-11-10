import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score
from datetime import datetime, timedelta
import random
import time
import json
import os
import requests

# ============================================================
# SAP COSTSHIELD AI | SUPPLY PROCUREMENT COMMAND CENTER
# Full demo / hackathon-ready Streamlit application
# ============================================================

st.set_page_config(
    page_title="SAP CostShield AI | Supply Procurement Command Center",
    page_icon="ðŸ›¡ï¸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------
# Theme / CSS
# -----------------------------
st.markdown("""
<style>
.stApp { background: #07111f; color: #e8f0f7; }
section[data-testid="stSidebar"] { background: #0a1626; }
.block-container { padding-top: 1rem; max-width: 1600px; }
h1,h2,h3 { color: #eaf4ff !important; }
.metric-card {
    background: linear-gradient(135deg,#0d2035,#102b45);
    border: 1px solid #1c496d; border-radius: 14px; padding: 18px;
    min-height: 125px; box-shadow: 0 8px 24px rgba(0,0,0,.18);
}
.metric-title { color:#8fb3cf; font-size:13px; text-transform:uppercase; letter-spacing:.6px; }
.metric-value { font-size:29px; font-weight:800; color:#fff; margin-top:6px; }
.metric-sub { font-size:12px; color:#8dd6ff; margin-top:6px; }
.alert-critical { background:#38151b; border-left:5px solid #ff4d5d; padding:13px; border-radius:9px; margin-bottom:8px; }
.alert-warning { background:#332a12; border-left:5px solid #ffbd45; padding:13px; border-radius:9px; margin-bottom:8px; }
.alert-ok { background:#123023; border-left:5px solid #35d48b; padding:13px; border-radius:9px; margin-bottom:8px; }
.terminal {
    background:#02070d; border:1px solid #16354f; border-radius:12px;
    padding:15px; font-family:monospace; color:#8ff0c2; height:280px;
    overflow:auto;
}
.badge { padding:4px 9px; border-radius:20px; font-size:11px; font-weight:700; }
.small { color:#8fa9bc; font-size:12px; }
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Helpers
# -----------------------------
def money(x):
    return f"${x:,.0f}"

def metric_card(title, value, subtitle=""):
    st.markdown(
        f"""<div class="metric-card">
        <div class="metric-title">{title}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-sub">{subtitle}</div>
        </div>""",
        unsafe_allow_html=True,
    )

def status_badge(status):
    m = {"CRITICAL":"ðŸ”´", "ELEVATED":"ðŸŸ ", "STABLE":"ðŸŸ¢", "MITIGATED":"ðŸ”µ"}
    return f"{m.get(status,'âšª')} {status}"

# ============================================================
# LIVE MONITORING DATA SERVICES
# ============================================================
REQUEST_TIMEOUT = 10

def _status(value, warning, critical):
    if value >= critical:
        return "CRITICAL"
    if value >= warning:
        return "WARNING"
    return "NORMAL"

def get_weather(latitude, longitude):
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        current = response.json().get("current", {})
        rain = float(current.get("precipitation", 0) or 0)
        wind = float(current.get("wind_speed_10m", 0) or 0)
        risk = min(100, rain * 20 + wind * 1.5)
        return {"source":"Open-Meteo","temperature_c":current.get("temperature_2m"),"humidity_pct":current.get("relative_humidity_2m"),"precipitation_mm":rain,"wind_speed_kmh":wind,"weather_code":current.get("weather_code"),"risk_score":round(risk,2),"status":_status(risk,30,60),"live":True,"updated_at":datetime.now().isoformat()}
    except Exception as exc:
        return {"source":"Open-Meteo","status":"UNAVAILABLE","risk_score":None,"live":False,"error":str(exc),"updated_at":datetime.now().isoformat()}

def get_traffic_status(latitude, longitude):
    if not os.getenv("TRAFFIC_API_KEY"):
        return {"source":"Traffic Provider","status":"CONFIG_REQUIRED","congestion_index":None,"live":False,"message":"Set TRAFFIC_API_KEY to enable a live traffic provider."}
    return {"source":"Traffic Provider","status":"CONFIG_REQUIRED","congestion_index":None,"live":False,"message":"Traffic provider adapter requires the selected provider endpoint/API schema."}

def get_factory_status(factory_name, production_capacity, current_load):
    utilization = 100.0 if production_capacity <= 0 else min(100.0, (current_load / production_capacity) * 100)
    return {"factory":factory_name,"production_capacity":production_capacity,"current_load":current_load,"utilization_pct":round(utilization,2),"status":_status(utilization,75,90),"live":True,"updated_at":datetime.now().isoformat()}

def get_port_status(port_name, congestion_index, vessel_queue, average_delay_hours):
    risk=min(100, congestion_index*0.60 + vessel_queue*2 + average_delay_hours*1.5)
    return {"port":port_name,"congestion_index":round(congestion_index,2),"vessel_queue":vessel_queue,"average_delay_hours":round(average_delay_hours,2),"risk_score":round(risk,2),"status":_status(risk,40,70),"live":True,"updated_at":datetime.now().isoformat()}

def get_live_monitoring(latitude, longitude, factory_name="Primary Supplier Factory", production_capacity=100, current_load=78, port_name="Mumbai JNPT", port_congestion=42, vessel_queue=8, port_delay_hours=12):
    weather=get_weather(latitude,longitude)
    traffic=get_traffic_status(latitude,longitude)
    factory=get_factory_status(factory_name,production_capacity,current_load)
    port=get_port_status(port_name,port_congestion,vessel_queue,port_delay_hours)
    scores=[]
    if weather.get("risk_score") is not None: scores.append(float(weather["risk_score"]))
    if traffic.get("congestion_index") is not None: scores.append(float(traffic["congestion_index"]))
    scores.extend([float(factory["utilization_pct"]),float(port["risk_score"])])
    overall=sum(scores)/len(scores) if scores else 0
    return {"updated_at":datetime.now().isoformat(),"overall_risk_score":round(overall,2),"overall_status":_status(overall,40,70),"weather":weather,"traffic":traffic,"factory":factory,"port":port}

# -----------------------------
# Data generation
# -----------------------------
@st.cache_data
def generate_data(n=180, seed=42):
    rng = np.random.default_rng(seed)
    suppliers = [
        ("Foxconn Precision Systems","Shenzhen","Power Inverter IC","Tier-1",92),
        ("Klaus Micro-Pneumatics","Munich","Hydraulic Actuator","Tier-1",88),
        ("Tata AutoComp Modules","Pune","EV Thermal Chassis","Tier-1",94),
        ("Kyoto Wafer & Sensor Corp","Kyoto","LiDAR Optical Array","Tier-2",90),
        ("TSMC Fab-18 Foundry","Tainan","5nm Logic Wafer","Tier-1",96),
        ("Antofagasta Lithium Refine","Santiago","Battery Grade Li2CO3","Tier-2",84),
        ("Rotterdam Euro-Chem","Rotterdam","Dielectric Coolant","Tier-3",81),
        ("UltraBuild Cement","Nagpur","Ready-Mix Concrete","Tier-1",89),
        ("MetroSteel Industries","Bhilai","Structural Steel","Tier-1",86),
        ("RoadCore Aggregates","Jabalpur","Aggregates","Tier-2",83),
    ]
    rows=[]
    for i in range(n):
        s = suppliers[i % len(suppliers)]
        order = int(rng.integers(25000, 650000))
        lead = int(rng.integers(3, 30))
        traffic = float(rng.uniform(5, 98))
        weather = float(rng.uniform(5, 95))
        factory = float(rng.uniform(45, 100))
        port = float(rng.uniform(5, 90))
        geo = float(rng.uniform(5, 75))
        esg = float(rng.uniform(60, 100))
        buffer = float(rng.uniform(1, 12))
        route = float(rng.uniform(10, 95))
        risk = (
            0.22*traffic + 0.18*weather + 0.18*(100-factory) +
            0.16*port + 0.12*geo + 0.08*route + 0.06*(100-esg)
        )
        risk = max(0, min(100, risk + rng.normal(0,5)))
        delay = max(0, (risk-35)/14 + rng.normal(0,0.6))
        delay = round(float(delay),1)
        var = max(0, order * (risk/100) * 0.38)
        status = "CRITICAL" if risk >= 68 else ("ELEVATED" if risk >= 42 else "STABLE")
        rows.append({
            "PO_Number": f"SAP-PO-{2026000+i}",
            "Supplier": s[0], "Supplier_City": s[1], "Material": s[2],
            "Tier": s[3], "Supplier_Reliability": s[4],
            "Destination": "Pune Construction Hub",
            "Order_Value_USD": order, "Planned_Lead_Time_Days": lead,
            "Traffic_Risk": round(traffic,1), "Weather_Risk": round(weather,1),
            "Factory_Capacity": round(factory,1), "Port_Bottleneck": round(port,1),
            "Geopolitical_Risk": round(geo,1), "ESG_Index": round(esg,1),
            "Inventory_Buffer_Days": round(buffer,1), "Route_Risk": round(route,1),
            "Disruption_Risk_Score": round(risk,1),
            "Predicted_Delay_Hours": delay,
            "Value_at_Risk_USD": round(var,0),
            "Status": status,
            "ETA": (datetime.now()+timedelta(days=lead, hours=delay)).strftime("%Y-%m-%d %H:%M"),
        })
    return pd.DataFrame(rows)

df = generate_data()

# -----------------------------
# Session state
# -----------------------------
if "mitigated_pos" not in st.session_state:
    st.session_state.mitigated_pos = set()
if "agent_logs" not in st.session_state:
    st.session_state.agent_logs = [
        "AURA AI engine initialized.",
        "SAP Event Mesh simulation connected.",
        "Predictive delay model ready.",
    ]
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = datetime.now()

# -----------------------------
# Sidebar controls
# -----------------------------
st.sidebar.title("ðŸ›¡ï¸ CostShield AI")
st.sidebar.caption("Supply Procurement Command Center")

page = st.sidebar.radio(
    "COMMAND CENTER",
    ["Executive Dashboard","Live Monitoring","Predictive Risk","Dynamic Rerouting",
     "Supplier Intelligence","Alerts & Actions","Business Impact","Data & AI Model"]
)

st.sidebar.divider()
st.sidebar.subheader("Global Stress Simulator")
traffic_shock = st.sidebar.slider("Traffic shock (%)", 0, 60, 10)
weather_shock = st.sidebar.slider("Weather shock (%)", 0, 60, 5)
capacity_shock = st.sidebar.slider("Factory capacity loss (%)", 0, 40, 5)
buffer_injection = st.sidebar.slider("Emergency buffer injection (days)", 0, 14, 2)
tier_filter = st.sidebar.multiselect("Supplier Tier", ["Tier-1","Tier-2","Tier-3"], default=["Tier-1","Tier-2","Tier-3"])
auto_refresh = st.sidebar.checkbox("Live simulation refresh", value=False)

# Apply stress
work = df.copy()
work["Traffic_Risk"] = np.minimum(100, work["Traffic_Risk"] + traffic_shock)
work["Weather_Risk"] = np.minimum(100, work["Weather_Risk"] + weather_shock)
work["Factory_Capacity"] = np.maximum(0, work["Factory_Capacity"] - capacity_shock)
work["Inventory_Buffer_Days"] += buffer_injection
work["Disruption_Risk_Score"] = (
    .22*work["Traffic_Risk"] + .18*work["Weather_Risk"] +
    .18*(100-work["Factory_Capacity"]) + .16*work["Port_Bottleneck"] +
    .12*work["Geopolitical_Risk"] + .08*work["Route_Risk"] +
    .06*(100-work["ESG_Index"])
).clip(0,100).round(1)
work["Predicted_Delay_Hours"] = np.maximum(0, (work["Disruption_Risk_Score"]-35)/14).round(1)
work["Value_at_Risk_USD"] = (work["Order_Value_USD"] * work["Disruption_Risk_Score"]/100 * .38).round(0)
work["Status"] = np.where(work["Disruption_Risk_Score"]>=68,"CRITICAL",
                   np.where(work["Disruption_Risk_Score"]>=42,"ELEVATED","STABLE"))
work.loc[work["PO_Number"].isin(st.session_state.mitigated_pos),"Status"]="MITIGATED"
work.loc[work["PO_Number"].isin(st.session_state.mitigated_pos),"Disruption_Risk_Score"]=18.5
work.loc[work["PO_Number"].isin(st.session_state.mitigated_pos),"Predicted_Delay_Hours"]=1.0
work.loc[work["PO_Number"].isin(st.session_state.mitigated_pos),"Value_at_Risk_USD"]=0

work = work[work["Tier"].isin(tier_filter)].reset_index(drop=True)

# -----------------------------
# Header
# -----------------------------
st.title("ðŸ›¡ï¸ SAP CostShield AI")
st.markdown("### AI-Driven Supply Procurement Command Center")
st.caption("Predict â†’ Alert â†’ Decide â†’ Reroute â†’ Protect Site Operations")
st.markdown(
    "**SAP BTP â€¢ S/4HANA OData v4 â€¢ Event Mesh â€¢ AI/ML â€¢ Logistics Intelligence**"
)

if auto_refresh:
    st.info("ðŸ”„ Live simulation mode enabled â€” data refreshes every 20 seconds.")
    time.sleep(0.2)

# ============================================================
# 1. EXECUTIVE DASHBOARD
# ============================================================
if page == "Executive Dashboard":
    critical = int((work.Status=="CRITICAL").sum())
    elevated = int((work.Status=="ELEVATED").sum())
    total_var = work.Value_at_Risk_USD.sum()
    avg_delay = work.Predicted_Delay_Hours.mean()
    idle_hours = critical * avg_delay
    potential_savings = total_var * .42

    cols = st.columns(6)
    for c, title, val, sub in zip(
        cols,
        ["Active POs","Critical Deliveries","At-Risk Value","Avg Delay","Site Idle Risk","Potential Savings"],
        [len(work),critical,money(total_var),f"{avg_delay:.1f}h",f"{idle_hours:.0f}h",money(potential_savings)],
        ["Live procurement pipeline", "Require immediate action", "Estimated financial exposure",
         "Predicted incoming delay", "Crew idle exposure", "Estimated avoided loss"]
    ):
        with c: metric_card(title,val,sub)

    st.divider()
    left,right = st.columns([1.3,1])
    with left:
        st.subheader("ðŸŒ Supply Risk Map / Network View")
        plot = work.groupby(["Supplier_City","Status"],as_index=False).size()
        fig = px.bar(plot,x="Supplier_City",y="size",color="Status",
                     title="Supplier risk distribution")
        st.plotly_chart(fig,use_container_width=True)
    with right:
        st.subheader("ðŸ“Š Risk Distribution")
        risk_counts = work.Status.value_counts().reset_index()
        risk_counts.columns=["Status","Count"]
        fig = px.pie(risk_counts,names="Status",values="Count",hole=.55)
        st.plotly_chart(fig,use_container_width=True)

    st.subheader("ðŸš¨ Top Procurement Risks")
    top = work.sort_values("Disruption_Risk_Score",ascending=False).head(10)
    show = top[["PO_Number","Supplier","Material","Traffic_Risk","Weather_Risk",
                "Factory_Capacity","Predicted_Delay_Hours","Value_at_Risk_USD","Status"]].copy()
    show["Status"] = show["Status"].map(status_badge)
    st.write(show.to_html(escape=False,index=False),unsafe_allow_html=True)

# ============================================================
# 2. LIVE MONITORING
# ============================================================
elif page == "Live Monitoring":
    st.subheader("ðŸŒ Live Supply Chain Monitoring")
    st.caption("Weather is live through Open-Meteo. Traffic requires a configured provider key; factory and port values are operational inputs until ERP/API adapters are connected.")

    loc1, loc2 = st.columns(2)
    with loc1:
        latitude = st.number_input("Monitoring Latitude", value=18.9750, format="%.4f")
    with loc2:
        longitude = st.number_input("Monitoring Longitude", value=72.8258, format="%.4f")

    with st.spinner("Updating live monitoring signals..."):
        live = get_live_monitoring(
            latitude=latitude,
            longitude=longitude,
            factory_name="Primary Supplier Factory",
            production_capacity=100,
            current_load=float(work["Factory_Capacity"].mean()),
            port_name="Mumbai JNPT",
            port_congestion=float(work["Port_Bottleneck"].mean()),
            vessel_queue=max(1, int(work["Port_Bottleneck"].mean()/10)),
            port_delay_hours=max(1, float(work["Predicted_Delay_Hours"].mean())),
        )

    w=live["weather"]; t=live["traffic"]; f=live["factory"]; p=live["port"]
    cols=st.columns(5)
    with cols[0]: metric_card("Overall Risk",f"{live['overall_risk_score']:.1f}",live["overall_status"])
    with cols[1]: metric_card("Temperature",f"{w.get('temperature_c','--')} Â°C","Open-Meteo live")
    with cols[2]: metric_card("Rainfall",f"{w.get('precipitation_mm','--')} mm","Current precipitation")
    with cols[3]: metric_card("Factory Utilization",f"{f['utilization_pct']:.1f}%",f["status"])
    with cols[4]: metric_card("Port Risk",f"{p['risk_score']:.1f}",f"Queue: {p['vessel_queue']}")

    st.divider()
    a,b,c,d=st.columns(4)
    with a:
        st.markdown("### ðŸŒ¦ï¸ Weather")
        st.write(f"Temperature: **{w.get('temperature_c','--')} Â°C**")
        st.write(f"Humidity: **{w.get('humidity_pct','--')}%**")
        st.write(f"Wind: **{w.get('wind_speed_kmh','--')} km/h**")
        st.write(f"Status: **{w.get('status','--')}**")
    with b:
        st.markdown("### ðŸš¦ Traffic")
        congestion=t.get("congestion_index")
        st.metric("Congestion", "--" if congestion is None else f"{congestion:.1f}%")
        st.write(f"Status: **{t.get('status','--')}**")
        if not t.get("live"):
            st.info(t.get("message","Traffic provider not configured."))
    with c:
        st.markdown("### ðŸ­ Factory")
        st.metric("Utilization",f"{f['utilization_pct']:.1f}%")
        st.write(f"Capacity: **{f['production_capacity']}**")
        st.write(f"Current load: **{f['current_load']:.1f}**")
        st.write(f"Status: **{f['status']}**")
    with d:
        st.markdown("### âš“ Port")
        st.metric("Congestion",f"{p['congestion_index']:.1f}%")
        st.metric("Vessel Queue",p["vessel_queue"])
        st.write(f"Avg delay: **{p['average_delay_hours']:.1f} h**")
        st.write(f"Status: **{p['status']}**")

    st.subheader("ðŸ“Š Live Risk Indicators")
    risk_data=pd.DataFrame({"System":["Weather","Factory","Port"],"Risk":[w.get("risk_score") or 0,f.get("utilization_pct") or 0,p.get("risk_score") or 0]})
    fig=px.bar(risk_data,x="System",y="Risk",text_auto=".1f",title="Current operational risk / utilization")
    st.plotly_chart(fig,use_container_width=True)

    st.subheader("ðŸ­ Supplier Production Capacity")
    cap=work.groupby("Supplier",as_index=False).agg(Factory_Capacity=("Factory_Capacity","mean"),Reliability=("Supplier_Reliability","mean")).sort_values("Factory_Capacity")
    fig=px.bar(cap,x="Factory_Capacity",y="Supplier",orientation="h",color="Reliability",title="Supplier capacity in current CostShield model")
    st.plotly_chart(fig,use_container_width=True)

    with st.expander("ðŸ”Ž Live payload"):
        st.json(live)
    st.caption(f"Last update: {live['updated_at']}")

# ============================================================
# 3. PREDICTIVE RISK
# ============================================================
elif page == "Predictive Risk":
    st.subheader("ðŸ¤– Predictive Delay Analysis")
    st.caption("Random Forest classifier trained on synthetic procurement risk data for this demo.")

    features = ["Traffic_Risk","Weather_Risk","Factory_Capacity","Port_Bottleneck",
                "Geopolitical_Risk","ESG_Index","Inventory_Buffer_Days","Route_Risk"]
    X = work[features].copy()
    y = (work["Disruption_Risk_Score"] >= 55).astype(int)

    if len(work) >= 20 and y.nunique() == 2:
        X_train,X_test,y_train,y_test=train_test_split(X,y,test_size=.25,random_state=42,stratify=y)
        model=RandomForestClassifier(n_estimators=180,max_depth=8,random_state=42,class_weight="balanced")
        model.fit(X_train,y_train)
        pred=model.predict(X_test)
        proba=model.predict_proba(X)[:,1]
        acc=accuracy_score(y_test,pred)
        f1=f1_score(y_test,pred)
    else:
        model=None
        proba=(work["Disruption_Risk_Score"]/100).values
        acc=f1=0

    a,b,c=st.columns(3)
    with a: metric_card("AI Risk Accuracy",f"{acc*100:.1f}%","Validation set")
    with b: metric_card("F1 Score",f"{f1:.2f}","Risk classification")
    with c: metric_card("High-Risk POs",str(int((proba>=.5).sum())),"AI probability â‰¥ 50%")

    work["AI_Delay_Probability"]=(proba*100).round(1)
    risk_table=work.sort_values("AI_Delay_Probability",ascending=False).head(20)
    st.dataframe(risk_table[["PO_Number","Supplier","Material","AI_Delay_Probability",
                              "Predicted_Delay_Hours","Disruption_Risk_Score","Value_at_Risk_USD","Status"]],
                 use_container_width=True,hide_index=True)

    if model is not None:
        imp=pd.DataFrame({"Feature":features,"Importance":model.feature_importances_}).sort_values("Importance",ascending=True)
        fig=px.bar(imp,x="Importance",y="Feature",orientation="h",title="AI feature importance")
        st.plotly_chart(fig,use_container_width=True)

# ============================================================
# 4. DYNAMIC REROUTING
# ============================================================
elif page == "Dynamic Rerouting":
    st.subheader("ðŸ—ºï¸ Dynamic Rerouting & Backup Supplier Engine")
    st.caption("Recommendation engine compares delay reduction against additional logistics cost.")

    critical = work.sort_values("Disruption_Risk_Score",ascending=False).head(15).copy()
    if critical.empty:
        st.success("No high-risk shipment requires rerouting.")
    else:
        selected = st.selectbox(
            "Select shipment / PO",
            critical.PO_Number.tolist()
        )
        row = critical[critical.PO_Number==selected].iloc[0]

        current_delay=float(row.Predicted_Delay_Hours)
        alt1=max(.3,current_delay*.42)
        alt2=max(.5,current_delay*.60)
        cost1=float(row.Order_Value_USD)*.012
        cost2=float(row.Order_Value_USD)*.007
        options=pd.DataFrame([
            ["Current Route",current_delay,0,current_delay,100],
            ["Alternative Route A",alt1,cost1,current_delay-alt1,round((current_delay-alt1)/max(current_delay,.1)*100,1)],
            ["Alternative Route B",alt2,cost2,current_delay-alt2,round((current_delay-alt2)/max(current_delay,.1)*100,1)],
        ],columns=["Option","Delay Hours","Extra Cost USD","Hours Saved","Risk Reduction %"])

        st.write(f"**PO:** {row.PO_Number}  |  **Supplier:** {row.Supplier}  |  **Material:** {row.Material}")
        st.dataframe(options,use_container_width=True,hide_index=True)

        best=options.iloc[1:].sort_values(["Hours Saved","Extra Cost USD"],ascending=[False,True]).iloc[0]
        st.success(
            f"ðŸ¤– **AI Recommendation:** {best['Option']} â€” save approximately "
            f"**{best['Hours Saved']:.1f} hours** with an estimated incremental cost of "
            f"**{money(best['Extra Cost USD'])}**."
        )

        st.subheader("ðŸ­ Backup Supplier Recommendation")
        backups=work[(work.Supplier!=row.Supplier) & (work.Material==row.Material)]
        if backups.empty:
            backups=work[work.Supplier!=row.Supplier].sort_values("Supplier_Reliability",ascending=False).head(5)
        else:
            backups=backups.sort_values("Supplier_Reliability",ascending=False).head(5)
        st.dataframe(backups[["Supplier","Supplier_City","Supplier_Reliability","Factory_Capacity",
                              "Predicted_Delay_Hours","Disruption_Risk_Score"]],
                     use_container_width=True,hide_index=True)

# ============================================================
# 5. SUPPLIER INTELLIGENCE
# ============================================================
elif page == "Supplier Intelligence":
    st.subheader("ðŸ­ Supplier Intelligence & Resilience")
    sup=work.groupby(["Supplier","Tier"],as_index=False).agg(
        POs=("PO_Number","count"),
        Reliability=("Supplier_Reliability","mean"),
        Capacity=("Factory_Capacity","mean"),
        Risk=("Disruption_Risk_Score","mean"),
        Delay=("Predicted_Delay_Hours","mean"),
        VaR=("Value_at_Risk_USD","sum")
    )
    sup["Health Score"]=(.45*sup.Reliability+.30*sup.Capacity+.25*(100-sup.Risk)).round(1)
    sup=sup.sort_values("Health Score",ascending=True)
    st.dataframe(sup,use_container_width=True,hide_index=True)

    fig=px.scatter(sup,x="Capacity",y="Risk",size="VaR",color="Health Score",
                   hover_name="Supplier",title="Supplier resilience matrix")
    st.plotly_chart(fig,use_container_width=True)

# ============================================================
# 6. ALERTS & ACTIONS
# ============================================================
elif page == "Alerts & Actions":
    st.subheader("ðŸš¨ Intelligent Alert Center")
    critical=work.sort_values("Disruption_Risk_Score",ascending=False).head(15)

    for _,r in critical.iterrows():
        if r.Status=="CRITICAL":
            st.markdown(
                f"""<div class="alert-critical"><b>ðŸ”´ CRITICAL â€” {r.PO_Number}</b><br>
                {r.Supplier} â†’ {r.Material}<br>
                Predicted delay: <b>{r.Predicted_Delay_Hours:.1f} hrs</b> |
                Traffic: {r.Traffic_Risk:.0f}% |
                Weather: {r.Weather_Risk:.0f}% |
                Factory capacity: {r.Factory_Capacity:.0f}% |
                Value at risk: <b>{money(r.Value_at_Risk_USD)}</b></div>""",
                unsafe_allow_html=True
            )
            if st.button(f"ðŸ›  Mitigate {r.PO_Number}",key=f"mit_{r.PO_Number}"):
                st.session_state.mitigated_pos.add(r.PO_Number)
                st.session_state.agent_logs.append(
                    f"{datetime.now():%H:%M:%S} | MITIGATION | {r.PO_Number} | Alternate route + buffer injected."
                )
                st.rerun()
        elif r.Status=="ELEVATED":
            st.markdown(
                f"""<div class="alert-warning"><b>ðŸŸ  ELEVATED â€” {r.PO_Number}</b><br>
                {r.Supplier} | Delay risk {r.Disruption_Risk_Score:.0f}% | ETA impact {r.Predicted_Delay_Hours:.1f} hrs</div>""",
                unsafe_allow_html=True
            )

    st.subheader("ðŸ§  AURA Agent Reasoning Terminal")
    logs = "<br>".join([f"[{x}]" for x in st.session_state.agent_logs[-30:]])
    st.markdown(f'<div class="terminal">{logs}</div>',unsafe_allow_html=True)

# ============================================================
# 7. BUSINESS IMPACT
# ============================================================
elif page == "Business Impact":
    st.subheader("ðŸ’° Procurement Resilience & Business Impact")
    critical=work[work.Status=="CRITICAL"]
    idle_hours=critical.Predicted_Delay_Hours.sum()
    labor_rate=125
    idle_cost=idle_hours*labor_rate
    spoilage_risk=(critical[critical.Material.str.contains("Concrete|Chemical|Battery",case=False,regex=True)].Order_Value_USD.sum()*.12)
    logistics_saving=work.Value_at_Risk_USD.sum()*.28
    total=idle_cost+spoilage_risk+logistics_saving

    cols=st.columns(4)
    with cols[0]: metric_card("Idle Hours Preventable",f"{idle_hours:.1f}h","Critical shipments")
    with cols[1]: metric_card("Labor Exposure",money(idle_cost),"At assumed site rate")
    with cols[2]: metric_card("Spoilage Exposure",money(spoilage_risk),"Time-sensitive materials")
    with cols[3]: metric_card("Potential Avoided Loss",money(total),"Combined estimated impact")

    st.divider()
    impact=pd.DataFrame({
        "Impact":["Idle Labor","Material Spoilage","Logistics Disruption"],
        "Exposure":[idle_cost,spoilage_risk,logistics_saving]
    })
    fig=px.bar(impact,x="Impact",y="Exposure",title="Financial impact prevented by proactive procurement")
    st.plotly_chart(fig,use_container_width=True)

    st.success(
        "ðŸŽ¯ Value proposition: CostShield changes procurement from reactive firefighting "
        "to predictive, data-driven resilience."
    )

# ============================================================
# 8. DATA & AI MODEL
# ============================================================
elif page == "Data & AI Model":
    st.subheader("ðŸ“¡ Data Integration & AI Model Center")
    st.write("Upload procurement data to run the dashboard on your own dataset.")

    uploaded=st.file_uploader("Upload CSV",type=["csv"])
    if uploaded:
        try:
            user_df=pd.read_csv(uploaded)
            st.success(f"Loaded {len(user_df):,} records.")
            st.dataframe(user_df.head(20),use_container_width=True)
        except Exception as e:
            st.error(f"Could not read CSV: {e}")

    st.subheader("ðŸ”Œ Integration Architecture")
    integrations=[
        ["SAP S/4HANA","Purchase Orders / Materials / Delivery Dates","Connected (Demo)"],
        ["SAP Event Mesh","Real-time procurement events","Connected (Demo)"],
        ["Traffic API","Route congestion / ETA","Simulation Adapter"],
        ["Weather API","Severe weather / precipitation","Simulation Adapter"],
        ["Supplier ERP","Factory capacity / output","Simulation Adapter"],
        ["Logistics Engine","Alternative routes / cost","AI Recommendation Engine"],
    ]
    st.table(pd.DataFrame(integrations,columns=["System","Data","Status"]))

    st.subheader("ðŸ§  AI Model Features")
    st.code(json.dumps({
        "model":"RandomForestClassifier",
        "prediction":"Supply delay risk",
        "features":[
            "Traffic risk","Weather risk","Factory capacity",
            "Port bottleneck","Geopolitical risk","ESG index",
            "Inventory buffer","Route risk"
        ],
        "decision_outputs":[
            "Delay probability","Expected delay hours",
            "Value at Risk","Rerouting recommendation",
            "Backup supplier recommendation"
        ]
    },indent=2))

# -----------------------------
# Footer
# -----------------------------
st.divider()
st.caption(
    f"ðŸ›¡ï¸ SAP CostShield AI â€¢ Last simulation update: {datetime.now():%Y-%m-%d %H:%M:%S} â€¢ "
    "Integrated decision-support application"
)

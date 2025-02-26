from flask import Flask, request, jsonify, render_template,send_file
import joblib
import pandas as pd
import json
import numpy as np
from sklearn.preprocessing import LabelEncoder, OneHotEncoder
import os

app = Flask(__name__, template_folder="templates")

# ================== Common Data Loading ==================
df = pd.read_csv("datasets/crop_production.csv")
df_clean = df.copy()
df_clean["State_Name"] = df_clean["State_Name"].str.strip()
df_clean["District_Name"] = df_clean["District_Name"].str.strip()
df_clean["Season"] = df_clean["Season"].str.strip()
df_clean["Crop"] = df_clean["Crop"].str.strip()

# ================== Yield Prediction Setup ==================
yield_model = joblib.load("models/optimized_crop_model.pkl")
state_district_yield = df_clean.groupby('State_Name')['District_Name'].apply(set).to_dict()

# Create label encoders for yield model
yield_encoders = {
    "State": LabelEncoder().fit(df_clean["State_Name"].unique()),
    "District": LabelEncoder().fit(df_clean["District_Name"].unique()),
    "Season": LabelEncoder().fit(df_clean["Season"].unique()),
    "Crop": LabelEncoder().fit(df_clean["Crop"].unique())
}

# ================== Crop Recommendation Setup ==================
recommend_model = joblib.load("models/crop_classification_model_xgb.joblib")
recommend_encoders = joblib.load("models/encoders_xgb.joblib")

# Lowercase validation data
df_lower = df_clean.copy()
df_lower["State_Name"] = df_lower["State_Name"].str.lower()
df_lower["District_Name"] = df_lower["District_Name"].str.lower()
state_district_recommend = df_lower.groupby('State_Name')['District_Name'].apply(set).to_dict()

# Recommendation encoders
state_to_code = {state: idx for idx, state in enumerate(sorted(df_lower["State_Name"].unique()))}
district_to_code = {district: idx for idx, district in enumerate(sorted(df_lower["District_Name"].unique()))}


# Create a dictionary mapping crops to PDF paths
CROP_GUIDES = {
    "Rice": "static/pdf/rice.pdf",
    "Wheat": "static/pdf/wheat.pdf",
    "Maize": "static/pdf/maize.pdf",
    "Apple":"static/pdf/apple.pdf",
    "Bajra":"static/pdf/bajra.pdf",
    "Banana":"static/pdf/banana.pdf",
    "Sugarcane":"static/pdf/sugarcane.pdf",
    "Urad":"static/pdf/urad.pdf",
    "Yam":"static/pdf/yam.pdf",
    "Paddy":"static/pdf/paddy.pdf",
    "Sunflower":"static/pdf/sunflower.pdf",
    "Beet Root":"static/pdf/beetroot.pdf",
    "Sweet potato":"static/pdf/sweetpotatoe.pdf",
    "Turmeric":"static/pdf/turmeric.pdf",
    "Ragi":"static/pdf/ragi.pdf",
    "Potato":"static/pdf/potato.pdf",
    "Dry chillies":"static/pdf/drychilli.pdf",
    "Ginger":"static/pdf/ginger.pdf",
    "Arecanut":"static/pdf/arecanut.pdf",
    "Soyabean":"static/pdf/soybean.pdf",
    "Sesamum":"static/pdf/sesamum.pdf",
    "Litchi":"static/pdf/litchi.pdf",
    "Garlic":"static/pdf/garlic.pdf",
    "Dry ginger":"static/pdf/dryginger.pdf",
    "Ber":"static/pdf/ber.pdf",
    "Arhar/Tur":"static/pdf/arhar.pdf",
    "Barley":"static/pdf/barley.pdf",
    "Cabbage":"static/pdf/cabbage.pdf",
    "Onion":"static/pdf/onion.pdf",
    "Ash Gourd":"static/pdf/ashgourd.pdf",
    "Tobacco":"static/pdf/tobacco.pdf",
    "Coconut":"static/pdf/coconut.pdf",
    "Castor seed":"static/pdf/Castorseed.pdf",
    "Tomato":"static/pdf/tomato.pdf",
    "Coffe":"static/pdf/coffe.pdf",
    "Tea":"static/pdf/tea.pdf",
    "Jute":"static/pdf/jute.pdf",
    "Mesta":"static/pdf/mesta.pdf",
    "Jowar":"static/pdf/jowar.pdf",
    "Mango":"static/pdf/mango.pdf",
    "Water Melon":"static/pdf/watermelon.pdf",
    "Jute & mesta":"static/pdf/jutemesta.pdf",
    "Gram":"static/pdf/gram.pdf",
    "Blackgram":"static/pdf/blackgram.pdf",
    "Horse-gram":"static/pdf/horsegram.pdf",
    "Moong(Green Gram)":"static/pdf/moong.pdf",
    "Cotton(lint)":"static/pdf/cotton.pdf",
}

@app.route('/download-strategy')
def download_strategy():
    crop = request.args.get('crop', '')
    file_path = CROP_GUIDES.get(crop.strip(), None)
    
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "Strategy not found"}), 404
        
    return send_file(file_path, as_attachment=True)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/model')
def model_page():
    return render_template('model.html',
        states=json.dumps(sorted(df_clean["State_Name"].unique().tolist())),
        districts=json.dumps(sorted(df_clean["District_Name"].unique().tolist())),
        seasons=json.dumps(sorted(df_clean["Season"].unique().tolist())),
        crops=json.dumps(sorted(df_clean["Crop"].unique().tolist()))
    )

@app.route('/autocomplete/<field>')
def autocomplete(field):
    query = request.args.get('query', '').lower()
    suggestions = []
    
    if field == 'state':
        suggestions = [s for s in df_clean["State_Name"].unique() if query in s.lower()]
    elif field == 'district':
        suggestions = [d for d in df_clean["District_Name"].unique() if query in d.lower()]
    elif field == 'season':
        suggestions = [s for s in df_clean["Season"].unique() if query in s.lower()]
    elif field == 'crop':
        suggestions = [c for c in df_clean["Crop"].unique() if query in c.lower()]
    
    return jsonify(suggestions[:15])

@app.route('/predict', methods=['POST'])
def predict():
    data = request.json
    result = {"yield": None, "crop": None, "error": None}

    try:
        state = data.get("State_Name", "").strip()
        district = data.get("District_Name", "").strip()
        
        # Validate state-district first
        valid_districts = state_district_yield.get(state, set())
        valid_districts_lower = state_district_recommend.get(state.lower(), set())
        
        if not state or not district:
            result["error"] = "State and District are required fields"
        elif district not in valid_districts or district.lower() not in valid_districts_lower:
            result["error"] = f"Invalid district for {state}. Valid districts: {', '.join(sorted(valid_districts))}"
        else:
            # ================== Yield Prediction Fix ==================
            try:
                # Create DataFrame with original column names
                input_df = pd.DataFrame([{
                    "State_Name": state,
                    "District_Name": district,
                    "Season": data.get("Season", "").strip(),
                    "Crop": data.get("Crop", "").strip(),
                    "Area": float(data.get("Area", 0)),
                    "Crop_Year": float(data.get("Crop_Year", 0))
                }])

                # Ensure correct column order as trained
                input_df = input_df[yield_model.feature_names_in_]

                # Predict using DataFrame
                prediction = yield_model.predict(input_df)[0]
                result["yield"] = f"{prediction:.2f} Tons"
            
            except Exception as e:
                result["error"] = f"Yield prediction error: {str(e)}"

            # ================== Crop Recommendation ==================
            try:
                if not result["error"]:  # Only recommend if validation passed
                    season_value = data.get("Season", "").lower()
                    season_encoded = recommend_encoders["Season"].transform([[season_value]])
                    season_features = season_encoded.toarray()[0] if hasattr(season_encoded, 'toarray') else season_encoded[0]

                    scaled_features = recommend_encoders["Scaler"].transform([[
                        float(data.get("Area", 0)),
                        float(data.get("Crop_Year", 0))
                    ]])[0]

                    input_features = np.concatenate([
                        [state_to_code[state.lower()]],
                        [district_to_code[district.lower()]],
                        scaled_features,
                        season_features
                    ]).reshape(1, -1)

                    pred = recommend_model.predict(input_features)[0]
                    result["crop"] = recommend_encoders["Crop"].inverse_transform([pred])[0]
            
            except Exception as e:
                if not result.get("yield"):  # Only show error if yield also failed
                    result["error"] = f"Prediction error: {str(e)}"

    except Exception as e:
        result["error"] = str(e)

    return jsonify(result)
if __name__ == '__main__':
    app.run(debug=True)
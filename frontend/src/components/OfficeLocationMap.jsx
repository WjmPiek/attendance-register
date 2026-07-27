import { useEffect, useRef, useState } from 'react';

let googleMapsPromise;

function loadGoogleMaps() {
  if (window.google?.maps) return Promise.resolve(window.google);

  if (!googleMapsPromise) {
    const apikey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
    googleMapsPromise = new Promise((resolve, reject) => {
      if (!apikey) return reject(new Error('Missing VITE_GOOGLE_MAPS_API_KEY'));
      const existingScript = document.querySelector('script[src*="maps.googleapis.com/maps/api/js"]');
      if (existingScript) {
        existingScript.addEventListener('load', () => resolve(window.google), { once: true });
        existingScript.addEventListener('error', reject, { once: true });
        return;
      }
      const script = document.createElement('script');
      script.src = `https://maps.googleapis.com/maps/api/js?key=${apikey}&libraries=places`;
      script.async = true;
      script.defer = true;
      script.onload = () => resolve(window.google);
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }
  return googleMapsPromise;
}

function geocodeAddress(google, address) {
  return new Promise((resolve) => {
    if (!address || !google.maps.Geocoder) return resolve(null);
    const geocoder = new google.maps.Geocoder();
    geocoder.geocode({ address: `${address}, South Africa`, region: 'ZA' }, (results, status) => {
      if (status === 'OK' && results?.[0]?.geometry?.location) {
        resolve({ location: results[0].geometry.location, formattedAddress: results[0].formatted_address });
      } else resolve(null);
    });
  });
}

export default function OfficeLocationMap({ office, onPick }) {
  const mapRef = useRef(null);
  const mapObjectRef = useRef(null);
  const markerRef = useRef(null);
  const circleRef = useRef(null);
  const googleRef = useRef(null);
  const [address, setAddress] = useState(office?.address || '');
  const [mapMessage, setMapMessage] = useState('');
  const [selectedPoint, setSelectedPoint] = useState(null);
  const hasApiKey = Boolean(import.meta.env.VITE_GOOGLE_MAPS_API_KEY);
  const fallbackMapUrl = address ? `https://www.google.com/maps?q=${encodeURIComponent(address)}&output=embed` : '';
  const openMapUrl = address ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}` : ''; 

  const placePoint = (latLng, formattedAddress = '') => {
    if (!latLng || !markerRef.current || !circleRef.current || !mapObjectRef.current) return;
    markerRef.current.setPosition(latLng);
    circleRef.current.setCenter(latLng);
    mapObjectRef.current.setCenter(latLng);
    mapObjectRef.current.setZoom(17);
    setSelectedPoint({ latitude: latLng.lat(), longitude: latLng.lng() });
    onPick({
      latitude: latLng.lat(),
      longitude: latLng.lng(),
      allowed_radius_m: Number(office.allowed_radius_m) || 100,
      formatted_address: formattedAddress,
    });
  };

  const findAddress = async () => {
    setMapMessage('Finding address...');
    try {
      const result = await geocodeAddress(googleRef.current || await loadGoogleMaps(), address.trim());
      if (!result) return setMapMessage('Google Maps could not find that address. Add the street number, suburb, city and postal code.');
      placePoint(result.location, result.formattedAddress);
      setAddress(result.formattedAddress || address);
      setMapMessage('Address found. Confirm the marker, then save the office location.');
    } catch (error) {
      setMapMessage(error.message || 'Unable to find address.');
    }
  };

  useEffect(() => {
    setAddress(office?.address || '');
    let cancelled = false;
    async function init() {
      const google = await loadGoogleMaps();
      googleRef.current = google;
      if (cancelled || !mapRef.current) return;

      const hasSavedGps = office.latitude !== null && office.latitude !== undefined && office.longitude !== null && office.longitude !== undefined;
      let center = hasSavedGps
        ? { lat: Number(office.latitude), lng: Number(office.longitude) }
        : { lat: -26.2041, lng: 28.0473 };

      // The complete office address is the source of truth when opening Set GPS.
      // This prevents an old/wrong coordinate from centering the map at another address.
      if (office.address) {
        const result = await geocodeAddress(google, office.address);
        if (cancelled) return;
        if (result) {
          center = { lat: result.location.lat(), lng: result.location.lng() };
          setAddress(result.formattedAddress || office.address);
          setMapMessage('Map centred on the office address. Drag the marker only if the entrance is elsewhere.');
        }
      }

      const map = new google.maps.Map(mapRef.current, { center, zoom: office.address || hasSavedGps ? 17 : 12 });
      const marker = new google.maps.Marker({ position: center, map, draggable: true });
      const circle = new google.maps.Circle({ map, center, radius: Number(office.allowed_radius_m) || 100, fillOpacity: 0.15, strokeWeight: 2 });
      mapObjectRef.current = map;
      markerRef.current = marker;
      circleRef.current = circle;
      setSelectedPoint({ latitude: center.lat, longitude: center.lng });

      const setLocation = (latLng) => placePoint(latLng);
      map.addListener('click', (e) => setLocation(e.latLng));
      marker.addListener('dragend', (e) => setLocation(e.latLng));
      onPick({ latitude: center.lat, longitude: center.lng, allowed_radius_m: Number(office.allowed_radius_m) || 100 });
    }
    if (hasApiKey) init().catch((err) => setMapMessage(err.message || 'Google Maps failed to load'));
    else setMapMessage('Interactive map needs a Google Maps API key. The live address preview below still works.');
    return () => { cancelled = true; };
  }, [office?.id, office?.address, office?.latitude, office?.longitude, office?.allowed_radius_m, onPick, hasApiKey]);

  return (
    <div className="office-location-map-shell">
      <div className="office-map-search-row">
        <label>
          Find the exact office address
          <input value={address} onChange={(event) => setAddress(event.target.value)} placeholder="Street number, street, suburb, city, postal code" />
        </label>
        {hasApiKey ? <button type="button" onClick={findAddress}>Find on Google Maps</button> : <a className="glass-button" href={openMapUrl} target="_blank" rel="noreferrer">Open in Google Maps</a>}
      </div>
      {mapMessage ? <p className="muted small">{mapMessage}</p> : null}
      {selectedPoint ? <p className="muted small">Proposed office GPS: {selectedPoint.latitude.toFixed(6)}, {selectedPoint.longitude.toFixed(6)}</p> : null}
      {hasApiKey ? <div style={{ height: 360, width: '100%', borderRadius: 16, overflow: 'hidden' }} ref={mapRef} /> : (fallbackMapUrl ? <iframe title="Business address map" src={fallbackMapUrl} loading="lazy" referrerPolicy="no-referrer-when-downgrade" style={{ height: 360, width: '100%', border: 0, borderRadius: 16 }} /> : null)}
    </div>
  );
}

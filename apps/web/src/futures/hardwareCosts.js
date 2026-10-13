/** EUR planning estimates, October 2026. Not vendor quotes; taxes/shipping/installation vary. */
export const hardwareBuilds = [
 {id:'ais',name:'Coastal AIS receiver',phase:'1 / pilot',purpose:'Receive and timestamp AIS traffic from a legal coastal site.',items:[
  ['RTL-SDR Blog V3 receiver, 2 units for dual-channel reception',2,35,'https://www.rtl-sdr.com/buy-rtl-sdr-dvb-t-dongles/','planning estimate; verify local seller'],
  ['Raspberry Pi 5 2 GB',1,75,'https://www.raspberrypi.com/news/price-increases-for-2gb-raspberry-pi-4-and-raspberry-pi-5/','official US MSRP $77.50, EUR allowance'],
  ['Power supply, case and SD card',1,42,null,'planning allowance'],
  ['Marine VHF/AIS antenna 162 MHz',1,95,null,'planning allowance'],
  ['Low-loss coax, connectors, filters and surge protection',1,105,null,'planning allowance'],
  ['Weatherproof enclosure and mounting',1,85,null,'planning allowance']
 ],recurring:'€5–20/month connectivity and energy where not provided; site access and installation excluded',notes:'AIS dual-channel design requires two tuned SDR receivers or a suitable dedicated dual-channel receiver. Line-of-sight and RF siting dominate coverage.'},
 {id:'radio',name:'Coastal radio monitoring station',phase:'1 / pilot',purpose:'Receive-only VHF/DSC metadata and a separate NAVTEX-capable chain where legally permitted.',items:[
  ['RTL-SDR Blog V3 for VHF reception',1,35,'https://www.rtl-sdr.com/buy-rtl-sdr-dvb-t-dongles/','planning estimate'],
  ['Raspberry Pi 5 2 GB',1,75,'https://www.raspberrypi.com/news/price-increases-for-2gb-raspberry-pi-4-and-raspberry-pi-5/','official US MSRP $77.50, EUR allowance'],
  ['VHF antenna, feedline and bandpass filter',1,150,null,'planning allowance'],
  ['HF receiver and NAVTEX antenna/filters',1,170,null,'planning allowance; separate HF receive path'],
  ['Power, enclosure, lightning protection and mounts',1,130,null,'planning allowance']
 ],recurring:'€5–25/month connectivity and energy; permissions/site fees excluded',notes:'NAVTEX operates on MF/HF and is not captured by a VHF-only antenna. Local monitoring and recording laws must be reviewed.'},
 {id:'drifter',name:'Recoverable Drifter buoy prototype',phase:'2 / prototype',purpose:'GNSS-tracked marine drifter for field testing, environmental sensing and drift-model validation.',items:[
  ['RAK WisBlock solar GPS tracker kit',1,82,'https://store.rakwireless.com/collections/kits-bundles','RAK kit listed $87, EUR allowance'],
  ['Pressure, temperature and IMU modules',1,95,null,'planning allowance'],
  ['Marine enclosure, seals, flotation and drogue',1,260,null,'prototype fabrication allowance'],
  ['Solar panel, battery, regulator and protection',1,125,null,'planning allowance'],
  ['Cellular or satellite tracker / modem',1,230,null,'planning allowance'],
  ['PCB, connectors, waterproof glands and assembly materials',1,140,null,'planning allowance'],
  ['Testing, marking and retrieval equipment',1,160,null,'planning allowance']
 ],recurring:'€10–60/month telemetry depending on cellular/satellite plan; launch, retrieval and vessel hire excluded',notes:'LoRa works only in range of an appropriate gateway; a free-drifting offshore buoy generally needs cellular or satellite connectivity. Prototype costs are not certified product costs.'},
 {id:'environment',name:'Coastal environmental station',phase:'2 / network',purpose:'Wind, pressure, air and water-temperature context for drift and satellite assessment.',items:[
  ['Raspberry Pi 5 2 GB',1,75,'https://www.raspberrypi.com/news/price-increases-for-2gb-raspberry-pi-4-and-raspberry-pi-5/','official US MSRP $77.50, EUR allowance'],
  ['Wind speed and direction instrument',1,150,null,'planning allowance'],
  ['Barometer, temperature and humidity sensors',1,65,null,'planning allowance'],
  ['Water temperature probe and cable',1,80,null,'planning allowance'],
  ['Outdoor enclosure, mounting, power and connectors',1,175,null,'planning allowance']
 ],recurring:'€5–20/month energy/connectivity; calibration and installation extra',notes:'This is a low-cost context station, not a calibrated oceanographic tide gauge.'},
 {id:'hydrophone',name:'Hydrophone research module',phase:'3 / research',purpose:'Optional passive underwater acoustic features for research, not automatic vessel identification.',items:[
  ['Hydrophone transducer',1,180,null,'planning allowance'],
  ['Low-noise preamp and audio ADC/recorder',1,230,null,'planning allowance'],
  ['Waterproof deployment housing, cables and mounts',1,220,null,'planning allowance'],
  ['Storage, power and edge processing',1,150,null,'planning allowance']
 ],recurring:'€5–30/month storage and uplink; marine deployment and recovery excluded',notes:'Research only. Check acoustic calibration, privacy, environmental permits and protected-species obligations.'},
 {id:'satellite',name:'Portable satellite validation kit',phase:'2 / integration',purpose:'Time-stamped field observations to corroborate or reject satellite/AIS hypotheses.',items:[
  ['GNSS logger / survey-capable receiver',1,180,null,'planning allowance'],
  ['Weatherproof camera / optical observation kit',1,250,null,'planning allowance'],
  ['Portable weather and location instruments',1,130,null,'planning allowance'],
  ['Power bank, cases and mounting',1,100,null,'planning allowance']
 ],recurring:'€0–15/month cloud storage/connectivity; field travel excluded',notes:'GNSS consumer accuracy is not survey-grade; provenance and consent are required.'},
 {id:'compute',name:'Resilient ingest and archive node',phase:'1 / scale',purpose:'Dedicated storage and processing for receiver data, queue replay and reproducible evidence workloads.',items:[
  ['Mini-PC, 16 GB RAM',1,320,null,'planning allowance'],
  ['2 TB SSD/NVMe',2,145,null,'planning allowance'],
  ['UPS and surge protection',1,145,null,'planning allowance'],
  ['Backup drive and network equipment',1,190,null,'planning allowance']
 ],recurring:'€15–90/month energy, backup storage and connectivity; managed cloud/VM can cost more',notes:'Compute alone does not resolve the current DB retention and scheduler issues; operational policy and monitoring are prerequisites.'}
];
export const totalCost = (build) => build.items.reduce((sum,item)=>sum+item[1]*item[2],0);
